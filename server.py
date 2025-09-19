from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta, time
from enum import Enum
import json

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'grocery_scheduler')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# Create the main app without a prefix
app = FastAPI(title="Grocery Scheduler API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

security = HTTPBearer()

# Models
class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday" 
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

class PreferredHours(BaseModel):
    start_time: str  # HH:MM format
    end_time: str    # HH:MM format
    days: List[DayOfWeek]

class UserPreferences(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    home_address: str
    preferred_stores: List[str]
    shopping_duration_minutes: int = 60
    preferred_hours: List[PreferredHours]
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())

class GroceryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    quantity: Optional[str] = None
    category: Optional[str] = None
    completed: bool = False

class GroceryList(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    items: List[GroceryItem] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())

class CalendarEvent(BaseModel):
    id: str
    title: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None

class GroceryStore(BaseModel):
    id: str
    name: str
    address: str
    lat: float
    lng: float
    distance_km: Optional[float] = None

class ScheduleSuggestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    suggested_time: datetime
    duration_minutes: int
    store: GroceryStore
    reason: str
    travel_time_minutes: int
    confidence_score: float

class WeeklySchedule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    week_start: datetime
    suggestions: List[ScheduleSuggestion]
    approved_suggestion_id: Optional[str] = None
    status: str = "pending"  # pending, approved, scheduled
    created_at: datetime = Field(default_factory=lambda: datetime.now())

# Mock Data
MOCK_CALENDAR_EVENTS = [
    CalendarEvent(
        id="1",
        title="Work Meeting",
        start_time=datetime.now() + timedelta(days=1, hours=9),
        end_time=datetime.now() + timedelta(days=1, hours=10),
        location="123 Business St, Downtown"
    ),
    CalendarEvent(
        id="2", 
        title="Gym Session",
        start_time=datetime.now() + timedelta(days=2, hours=18),
        end_time=datetime.now() + timedelta(days=2, hours=19),
        location="456 Fitness Ave, Midtown"
    ),
    CalendarEvent(
        id="3",
        title="Dinner with Friends",
        start_time=datetime.now() + timedelta(days=3, hours=19),
        end_time=datetime.now() + timedelta(days=3, hours=21),
        location="789 Restaurant Row, Uptown"
    )
]

MOCK_GROCERY_STORES = [
    GroceryStore(id="1", name="Whole Foods Market", address="100 Organic St", lat=40.7128, lng=-74.0060),
    GroceryStore(id="2", name="Trader Joe's", address="200 Affordable Ave", lat=40.7589, lng=-73.9851),
    GroceryStore(id="3", name="Safeway", address="300 Convenient Blvd", lat=40.7505, lng=-73.9934),
    GroceryStore(id="4", name="Target Grocery", address="400 Everything Dr", lat=40.7282, lng=-73.7949)
]

# Services
class SchedulingService:
    @staticmethod
    def calculate_travel_time(from_location: str, to_store: GroceryStore) -> int:
        """Mock travel time calculation"""
        return 15  # Mock 15 minutes travel time
    
    @staticmethod
    def find_nearby_stores(location: str) -> List[GroceryStore]:
        """Mock store finding based on location"""
        return MOCK_GROCERY_STORES[:2]  # Return first 2 stores as "nearby"
    
    @staticmethod
    def get_calendar_events(user_id: str, start_date: datetime, end_date: datetime) -> List[CalendarEvent]:
        """Mock calendar events"""
        return [event for event in MOCK_CALENDAR_EVENTS if start_date <= event.start_time <= end_date]
    
    @staticmethod
    def generate_schedule_suggestions(preferences: UserPreferences, week_start: datetime) -> List[ScheduleSuggestion]:
        """Generate grocery shopping suggestions for the week"""
        suggestions = []
        week_end = week_start + timedelta(days=7)
        
        # Get calendar events for the week
        events = SchedulingService.get_calendar_events(preferences.user_id, week_start, week_end)
        
        # For each day, check if it's a preferred shopping day
        for day_offset in range(7):
            current_date = week_start + timedelta(days=day_offset)
            day_name = current_date.strftime('%A').lower()
            
            # Check if this day is in preferred hours
            preferred_for_day = [ph for ph in preferences.preferred_hours if day_name in [d.value for d in ph.days]]
            
            if not preferred_for_day:
                continue
                
            # For each preferred hour window on this day
            for pref_hours in preferred_for_day:
                start_time = datetime.strptime(pref_hours.start_time, "%H:%M").time()
                end_time = datetime.strptime(pref_hours.end_time, "%H:%M").time()
                
                # Create potential shopping slots
                current_time = datetime.combine(current_date.date(), start_time)
                slot_end = datetime.combine(current_date.date(), end_time)
                
                while current_time + timedelta(minutes=preferences.shopping_duration_minutes) <= slot_end:
                    # Check if this slot conflicts with calendar events
                    slot_start = current_time
                    slot_end_time = current_time + timedelta(minutes=preferences.shopping_duration_minutes)
                    
                    conflicts = [e for e in events if (
                        (slot_start <= e.start_time <= slot_end_time) or
                        (slot_start <= e.end_time <= slot_end_time) or
                        (e.start_time <= slot_start and e.end_time >= slot_end_time)
                    )]
                    
                    if not conflicts:
                        # Find nearby stores (could be based on home or recent event locations)
                        stores = SchedulingService.find_nearby_stores(preferences.home_address)
                        
                        for store in stores:
                            travel_time = SchedulingService.calculate_travel_time(preferences.home_address, store)
                            confidence = 0.8 if day_name in ['saturday', 'sunday'] else 0.6
                            
                            suggestion = ScheduleSuggestion(
                                suggested_time=slot_start,
                                duration_minutes=preferences.shopping_duration_minutes,
                                store=store,
                                reason=f"Free time on {current_date.strftime('%A')} during your preferred hours",
                                travel_time_minutes=travel_time,
                                confidence_score=confidence
                            )
                            suggestions.append(suggestion)
                    
                    current_time += timedelta(hours=1)  # Move to next hour slot
        
        # Sort by confidence score and return top suggestions
        return sorted(suggestions, key=lambda x: x.confidence_score, reverse=True)[:5]

def prepare_for_mongo(data: dict) -> dict:
    """Convert datetime objects to ISO strings for MongoDB storage"""
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    data[key][i] = prepare_for_mongo(item)
    return data

def parse_from_mongo(data: dict) -> dict:
    """Convert ISO strings back to datetime objects"""
    for key, value in data.items():
        if isinstance(value, str) and key.endswith(('_at', '_time')):
            try:
                data[key] = datetime.fromisoformat(value)
            except:
                pass
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    data[key][i] = parse_from_mongo(item)
    return data

# Routes
@api_router.post("/preferences", response_model=UserPreferences)
async def create_preferences(preferences: UserPreferences):
    """Create or update user preferences"""
    existing = await db.preferences.find_one({"user_id": preferences.user_id})
    
    preferences_dict = preferences.dict()
    preferences_dict = prepare_for_mongo(preferences_dict)
    
    if existing:
        preferences_dict["updated_at"] = datetime.now().isoformat()
        await db.preferences.update_one(
            {"user_id": preferences.user_id},
            {"$set": preferences_dict}
        )
    else:
        await db.preferences.insert_one(preferences_dict)
    
    return preferences

@api_router.get("/preferences/{user_id}", response_model=UserPreferences)
async def get_preferences(user_id: str):
    """Get user preferences"""
    preferences = await db.preferences.find_one({"user_id": user_id})
    if not preferences:
        raise HTTPException(status_code=404, detail="Preferences not found")
    
    preferences = parse_from_mongo(preferences)
    return UserPreferences(**preferences)

@api_router.post("/grocery-list", response_model=GroceryList)
async def create_grocery_list(grocery_list: GroceryList):
    """Create or update grocery list"""
    existing = await db.grocery_lists.find_one({"user_id": grocery_list.user_id})
    
    list_dict = grocery_list.dict()
    list_dict = prepare_for_mongo(list_dict)
    
    if existing:
        list_dict["updated_at"] = datetime.now().isoformat()
        await db.grocery_lists.update_one(
            {"user_id": grocery_list.user_id},
            {"$set": list_dict}
        )
    else:
        await db.grocery_lists.insert_one(list_dict)
    
    return grocery_list

@api_router.get("/grocery-list/{user_id}", response_model=GroceryList)
async def get_grocery_list(user_id: str):
    """Get user's grocery list"""
    grocery_list = await db.grocery_lists.find_one({"user_id": user_id})
    if not grocery_list:
        # Return empty list if none exists
        return GroceryList(user_id=user_id, items=[])
    
    grocery_list = parse_from_mongo(grocery_list)
    return GroceryList(**grocery_list)

@api_router.post("/schedule/generate/{user_id}")
async def generate_weekly_schedule(user_id: str):
    """Generate weekly grocery shopping schedule"""
    # Get user preferences
    preferences = await db.preferences.find_one({"user_id": user_id})
    if not preferences:
        raise HTTPException(status_code=404, detail="User preferences not found")
    
    preferences = parse_from_mongo(preferences)
    user_prefs = UserPreferences(**preferences)
    
    # Calculate week start (Monday)
    today = datetime.now()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Generate suggestions
    suggestions = SchedulingService.generate_schedule_suggestions(user_prefs, week_start)
    
    # Create weekly schedule
    schedule = WeeklySchedule(
        user_id=user_id,
        week_start=week_start,
        suggestions=suggestions
    )
    
    # Save to database
    schedule_dict = schedule.dict()
    schedule_dict = prepare_for_mongo(schedule_dict)
    
    # Remove existing schedule for this week
    await db.weekly_schedules.delete_many({
        "user_id": user_id,
        "week_start": week_start.isoformat()
    })
    
    await db.weekly_schedules.insert_one(schedule_dict)
    
    return {"message": "Schedule generated successfully", "suggestions_count": len(suggestions)}

@api_router.get("/schedule/{user_id}", response_model=WeeklySchedule)
async def get_weekly_schedule(user_id: str):
    """Get current weekly schedule"""
    # Calculate current week start
    today = datetime.now()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    schedule = await db.weekly_schedules.find_one({
        "user_id": user_id,
        "week_start": week_start.isoformat()
    })
    
    if not schedule:
        raise HTTPException(status_code=404, detail="No schedule found for current week")
    
    schedule = parse_from_mongo(schedule)
    return WeeklySchedule(**schedule)

@api_router.post("/schedule/approve/{schedule_id}/{suggestion_id}")
async def approve_suggestion(schedule_id: str, suggestion_id: str):
    """Approve a grocery shopping suggestion"""
    # Update schedule with approved suggestion
    result = await db.weekly_schedules.update_one(
        {"id": schedule_id},
        {
            "$set": {
                "approved_suggestion_id": suggestion_id,
                "status": "approved"
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    return {"message": "Suggestion approved successfully"}

@api_router.get("/stores")
async def get_grocery_stores():
    """Get list of available grocery stores"""
    return MOCK_GROCERY_STORES

@api_router.get("/")
async def root():
    return {"message": "Grocery Scheduler API"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    