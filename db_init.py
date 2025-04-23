import os
import argparse
import datetime
import bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv
from bson.objectid import ObjectId

####################################################################################################
# Load Environment Variables
####################################################################################################
load_dotenv()

# Database connection details
MONGODB_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'spotify_clone')

####################################################################################################
# Database Connection
####################################################################################################
def connect_to_mongodb():
    """Connect to MongoDB and return client and db objects"""
    try:
        print(f"Connecting to MongoDB: {MONGODB_URI}")
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        
        # Verify connection
        client.admin.command('ping')
        print("MongoDB connection successful!")
        
        # Get or create database
        db = client[DATABASE_NAME]
        print(f"Using database: {DATABASE_NAME}")
        
        return client, db
    except Exception as e:
        print(f"Error connecting to MongoDB: {str(e)}")
        raise

####################################################################################################
# Collection Creation
####################################################################################################
def create_collections(db):
    """Create collections if they don't exist"""
    print("\nCreating collections...")
    
    # List of collections to create
    collections = ['users', 'songs', 'playlists', 'activity_logs']
    
    existing_collections = db.list_collection_names()
    
    for collection_name in collections:
        if collection_name not in existing_collections:
            db.create_collection(collection_name)
            print(f"Created collection: {collection_name}")
        else:
            print(f"Collection already exists: {collection_name}")

####################################################################################################
# Sample Data Creation
####################################################################################################
def create_admin_user(db):
    """Create admin user if not exists"""
    print("\nChecking for admin user...")
    
    users = db.users
    admin = users.find_one({"email": "admin@spotify.com"})
    
    if not admin:
        # Create admin user
        hashed_password = bcrypt.hashpw("Admin@123".encode('utf-8'), bcrypt.gensalt(12))
        
        admin_user = {
            "_id": ObjectId(),
            "name": "Admin User",
            "email": "admin@spotify.com",
            "phone": "+1234567890",
            "password": hashed_password,
            "is_admin": True,
            "created_at": datetime.datetime.utcnow(),
            "last_login": None,
            "login_attempts": 0,
            "account_locked": False
        }
        
        users.insert_one(admin_user)
        print("Admin user created!")
    else:
        print("Admin user already exists")

def create_sample_users(db, count=5):
    """Create sample regular users"""
    print(f"\nCreating {count} sample users...")
    
    users = db.users
    existing_count = users.count_documents({"is_admin": False})
    
    if existing_count >= count:
        print(f"Already have {existing_count} non-admin users, skipping creation")
        return
    
    # Sample user data
    sample_users = [
        {
            "name": "John Smith",
            "email": "john@example.com",
            "phone": "+1234567001",
            "password": "Password@123",
        },
        {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1234567002",
            "password": "Password@123",
        },
        {
            "name": "Bob Johnson",
            "email": "bob@example.com",
            "phone": "+1234567003",
            "password": "Password@123",
        },
        {
            "name": "Alice Williams",
            "email": "alice@example.com",
            "phone": "+1234567004",
            "password": "Password@123",
        },
        {
            "name": "Charlie Brown",
            "email": "charlie@example.com",
            "phone": "+1234567005",
            "password": "Password@123",
        }
    ]
    
    for user_data in sample_users[:count]:
        # Check if user already exists
        if users.find_one({"email": user_data["email"]}):
            print(f"User {user_data['email']} already exists, skipping")
            continue
            
        # Hash password
        hashed_password = bcrypt.hashpw(user_data["password"].encode('utf-8'), bcrypt.gensalt(12))
        
        # Create user document
        user = {
            "_id": ObjectId(),
            "name": user_data["name"],
            "email": user_data["email"],
            "phone": user_data["phone"],
            "password": hashed_password,
            "is_admin": False,
            "created_at": datetime.datetime.utcnow(),
            "last_login": None,
            "login_attempts": 0,
            "account_locked": False
        }
        
        users.insert_one(user)
        print(f"Created user: {user_data['email']}")

def create_sample_songs(db, count=10):
    """Create sample songs"""
    print(f"\nCreating {count} sample songs...")
    
    songs = db.songs
    existing_count = songs.count_documents({})
    
    if existing_count >= count:
        print(f"Already have {existing_count} songs, skipping creation")
        return
    
    # Sample song data
    sample_songs = [
        {
            "title": "Summer Vibes",
            "artist": "Beach Waves",
            "mood": "Happy",
            "file_path": "Happy_(mood)/summer_vibes.mp3",
            "image_path": "Happy_(mood)/summer_vibes.jpg"
        },
        {
            "title": "Rainy Day",
            "artist": "Cloud Nine",
            "mood": "Sad",
            "file_path": "Sad_(mood)/rainy_day.mp3",
            "image_path": "Sad_(mood)/rainy_day.jpg"
        },
        {
            "title": "Workout Mix",
            "artist": "Fitness Kings",
            "mood": "Energetic",
            "file_path": "Energetic_(mood)/workout_mix.mp3",
            "image_path": "Energetic_(mood)/workout_mix.jpg"
        },
        {
            "title": "Study Session",
            "artist": "Focus Masters",
            "mood": "Focus",
            "file_path": "Focus_(mood)/study_session.mp3",
            "image_path": "Focus_(mood)/study_session.jpg"
        },
        {
            "title": "Night Drive",
            "artist": "Midnight Cruisers",
            "mood": "Chill",
            "file_path": "Chill_(mood)/night_drive.mp3",
            "image_path": "Chill_(mood)/night_drive.jpg"
        },
        {
            "title": "Epic Battle",
            "artist": "Warriors",
            "mood": "Angry",
            "file_path": "Angry_(mood)/epic_battle.mp3",
            "image_path": "Angry_(mood)/epic_battle.jpg"
        },
        {
            "title": "Love Song",
            "artist": "Romantics",
            "mood": "Romantic",
            "file_path": "Romantic_(mood)/love_song.mp3",
            "image_path": "Romantic_(mood)/love_song.jpg"
        },
        {
            "title": "Dark Thoughts",
            "artist": "The Shadows",
            "mood": "Dark",
            "file_path": "Dark_(mood)/dark_thoughts.mp3",
            "image_path": "Dark_(mood)/dark_thoughts.jpg"
        },
        {
            "title": "Morning Sunshine",
            "artist": "Daybreak",
            "mood": "Bright",
            "file_path": "Bright_(mood)/morning_sunshine.mp3",
            "image_path": "Bright_(mood)/morning_sunshine.jpg"
        },
        {
            "title": "Groovy Beats",
            "artist": "Funk Masters",
            "mood": "Funky",
            "file_path": "Funky_(mood)/groovy_beats.mp3",
            "image_path": "Funky_(mood)/groovy_beats.jpg"
        }
    ]
    
    for song_data in sample_songs[:count]:
        # Check if song already exists
        if songs.find_one({"title": song_data["title"], "artist": song_data["artist"]}):
            print(f"Song '{song_data['title']}' by {song_data['artist']} already exists, skipping")
            continue
        
        # Create song document
        song = {
            "_id": ObjectId(),
            "title": song_data["title"],
            "artist": song_data["artist"],
            "mood": song_data["mood"],
            "file_path": song_data["file_path"],
            "image_path": song_data["image_path"],
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow(),
            "plays": 0,
            "duration": None
        }
        
        songs.insert_one(song)
        print(f"Created song: '{song_data['title']}' by {song_data['artist']}")
        
        # Create mood directory if it doesn't exist
        mood_dir = os.path.join("static", "songs", f"{song_data['mood']}_(mood)")
        os.makedirs(mood_dir, exist_ok=True)
        print(f"Ensured directory exists: {mood_dir}")

def create_sample_playlists(db, count=3):
    """Create sample playlists"""
    print(f"\nCreating {count} sample playlists...")
    
    playlists = db.playlists
    users = db.users
    songs = db.songs
    
    existing_count = playlists.count_documents({})
    if existing_count >= count:
        print(f"Already have {existing_count} playlists, skipping creation")
        return
    
    # Get users (non-admin)
    user_list = list(users.find({"is_admin": False}, {"_id": 1, "name": 1}))
    if not user_list:
        print("No users found to create playlists for, skipping")
        return
    
    # Get songs
    song_list = list(songs.find({}, {"_id": 1, "title": 1, "artist": 1}))
    if not song_list:
        print("No songs found to add to playlists, skipping")
        return
    
    # Sample playlist templates
    playlist_templates = [
        {
            "name": "My Favorites",
            "description": "A collection of my favorite songs",
            "is_public": True
        },
        {
            "name": "Workout Mix",
            "description": "Songs to keep me motivated during workouts",
            "is_public": True
        },
        {
            "name": "Chill Vibes",
            "description": "Relaxing songs for winding down",
            "is_public": False
        }
    ]
    
    import random
    
    # Create playlists
    for i, template in enumerate(playlist_templates[:count]):
        user = random.choice(user_list)
        
        # Check if user already has this playlist
        if playlists.find_one({"name": template["name"], "user_id": str(user["_id"])}):
            print(f"User {user['name']} already has playlist '{template['name']}', skipping")
            continue
        
        # Select random songs (between 3 and 5)
        playlist_songs = random.sample(
            [str(song["_id"]) for song in song_list], 
            min(random.randint(3, 5), len(song_list))
        )
        
        # Create playlist document
        playlist = {
            "_id": ObjectId(),
            "name": template["name"],
            "user_id": str(user["_id"]),
            "description": template["description"],
            "is_public": template["is_public"],
            "cover_image": None,
            "songs": playlist_songs,
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow()
        }
        
        playlists.insert_one(playlist)
        
        song_titles = [
            next(s["title"] for s in song_list if str(s["_id"]) == song_id)
            for song_id in playlist_songs
        ]
        
        print(f"Created playlist '{template['name']}' for user {user['name']} with {len(playlist_songs)} songs:")
        for title in song_titles:
            print(f"  - {title}")

####################################################################################################
# Main Function
####################################################################################################
def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Initialize Spotify Database')
    parser.add_argument('--reset', action='store_true', help='Drop existing collections before creating new ones')
    parser.add_argument('--with-samples', action='store_true', help='Create sample data')
    
    args = parser.parse_args()
    
    try:
        # Connect to MongoDB
        client, db = connect_to_mongodb()
        
        # Reset database if requested
        if args.reset:
            print("\nResetting database...")
            for collection in db.list_collection_names():
                db.drop_collection(collection)
                print(f"Dropped collection: {collection}")
        
        # Create collections
        create_collections(db)
        
        # Create admin user
        create_admin_user(db)
        
        # Create sample data if requested
        if args.with_samples:
            create_sample_users(db)
            create_sample_songs(db)
            create_sample_playlists(db)
        
        print("\nDatabase initialization complete!")
        
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
    finally:
        if 'client' in locals():
            client.close()
            print("MongoDB connection closed")

if __name__ == "__main__":
    main() 