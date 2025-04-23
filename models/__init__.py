# Empty file to make the directory a Python package

from pymongo import MongoClient, IndexModel, ASCENDING, DESCENDING, TEXT
from config import Config
import logging
import os

####################################################################################################
# Database Connection
####################################################################################################
try:
    # Setup logging
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    logging.basicConfig(
        filename=os.path.join(log_dir, 'database.log'),
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Connect to MongoDB using Config class
    client = MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')  # Verify connection
    
    # Get database
    db = client[Config.DATABASE_NAME]
    
    logging.info(f"Connected to MongoDB database: {Config.DATABASE_NAME}")
    
    ####################################################################################################
    # Collection Definitions and Indexes
    ####################################################################################################
    
    # Users Collection
    users_collection = db['users']
    
    # Define indexes for users collection
    user_indexes = [
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("name", TEXT)]),  # Text index for search
        IndexModel([("created_at", DESCENDING)]),  # Sort by newest
        IndexModel([("is_admin", ASCENDING)])  # Query admins quickly
    ]
    
    # Songs Collection
    songs_collection = db['songs']
    
    # Define indexes for songs collection
    song_indexes = [
        IndexModel([("title", TEXT), ("artist", TEXT)]),  # Text search on title and artist
        IndexModel([("mood", ASCENDING)]),  # Query by mood
        IndexModel([("created_at", DESCENDING)]),  # Sort by newest
        IndexModel([("plays", DESCENDING)])  # Sort by popularity
    ]
    
    # Playlists Collection
    playlists_collection = db['playlists']
    
    # Define indexes for playlists collection
    playlist_indexes = [
        IndexModel([("user_id", ASCENDING)]),  # Query playlists by user
        IndexModel([("name", TEXT)]),  # Text search on playlist name
        IndexModel([("created_at", DESCENDING)])  # Sort by newest
    ]
    
    # Activity Logs Collection
    logs_collection = db['activity_logs']
    
    # Define indexes for logs collection
    log_indexes = [
        IndexModel([("user_id", ASCENDING)]),  # Query logs by user
        IndexModel([("action_type", ASCENDING)]),  # Query by action type
        IndexModel([("timestamp", DESCENDING)]),  # Sort by newest
        IndexModel([("resource_type", ASCENDING)])  # Query by resource type
    ]
    
    ####################################################################################################
    # Create Indexes
    ####################################################################################################
    # Create indexes
    try:
        users_collection.create_indexes(user_indexes)
        logging.info("Created indexes for users collection")
    except Exception as e:
        logging.error(f"Error creating user indexes: {str(e)}")
    
    try:
        songs_collection.create_indexes(song_indexes)
        logging.info("Created indexes for songs collection")
    except Exception as e:
        logging.error(f"Error creating song indexes: {str(e)}")
    
    try:
        playlists_collection.create_indexes(playlist_indexes)
        logging.info("Created indexes for playlists collection")
    except Exception as e:
        logging.error(f"Error creating playlist indexes: {str(e)}")
    
    try:
        logs_collection.create_indexes(log_indexes)
        logging.info("Created indexes for logs collection")
    except Exception as e:
        logging.error(f"Error creating log indexes: {str(e)}")
    
    ####################################################################################################
    # Collection Schema Validation
    ####################################################################################################
    # User collection validation schema
    user_schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "email", "password"],
            "properties": {
                "name": {
                    "bsonType": "string",
                    "description": "User's full name"
                },
                "email": {
                    "bsonType": "string",
                    "description": "User's email address (must be unique)"
                },
                "phone": {
                    "bsonType": "string",
                    "description": "User's phone number"
                },
                "password": {
                    "bsonType": "binData",
                    "description": "Hashed password"
                },
                "is_admin": {
                    "bsonType": "bool",
                    "description": "Whether the user is an admin"
                },
                "created_at": {
                    "bsonType": "date",
                    "description": "User creation timestamp"
                },
                "last_login": {
                    "bsonType": ["date", "null"],
                    "description": "Last login timestamp"
                },
                "login_attempts": {
                    "bsonType": "int",
                    "description": "Number of consecutive failed login attempts"
                },
                "account_locked": {
                    "bsonType": "bool",
                    "description": "Whether the account is locked due to too many failed login attempts"
                },
                "lock_expires_at": {
                    "bsonType": "date",
                    "description": "When the account lock expires"
                }
            }
        }
    }
    
    # Song collection validation schema
    song_schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["title", "artist", "mood", "file_path"],
            "properties": {
                "title": {
                    "bsonType": "string",
                    "description": "Song title"
                },
                "artist": {
                    "bsonType": "string",
                    "description": "Artist name"
                },
                "mood": {
                    "bsonType": "string",
                    "description": "Song mood/category"
                },
                "file_path": {
                    "bsonType": "string",
                    "description": "Path to the song file"
                },
                "image_path": {
                    "bsonType": ["string", "null"],
                    "description": "Path to the song cover image"
                },
                "created_at": {
                    "bsonType": "date",
                    "description": "Song creation timestamp"
                },
                "updated_at": {
                    "bsonType": "date",
                    "description": "Song last update timestamp"
                },
                "plays": {
                    "bsonType": "int",
                    "description": "Number of times the song has been played"
                },
                "duration": {
                    "bsonType": ["int", "null"],
                    "description": "Song duration in seconds"
                }
            }
        }
    }
    
    # Playlist collection validation schema
    playlist_schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "user_id", "songs"],
            "properties": {
                "name": {
                    "bsonType": "string",
                    "description": "Playlist name"
                },
                "user_id": {
                    "bsonType": "string",
                    "description": "ID of the user who created the playlist"
                },
                "description": {
                    "bsonType": ["string", "null"],
                    "description": "Playlist description"
                },
                "is_public": {
                    "bsonType": "bool",
                    "description": "Whether the playlist is public"
                },
                "cover_image": {
                    "bsonType": ["string", "null"],
                    "description": "Path to the playlist cover image"
                },
                "songs": {
                    "bsonType": "array",
                    "description": "Array of song IDs in the playlist",
                    "items": {
                        "bsonType": "string"
                    }
                },
                "created_at": {
                    "bsonType": "date",
                    "description": "Playlist creation timestamp"
                },
                "updated_at": {
                    "bsonType": "date",
                    "description": "Playlist last update timestamp"
                }
            }
        }
    }
    
    # Activity log collection validation schema
    log_schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "action_type", "timestamp"],
            "properties": {
                "user_id": {
                    "bsonType": "string",
                    "description": "ID of the user who performed the action"
                },
                "action_type": {
                    "bsonType": "string",
                    "description": "Type of action performed (e.g., 'login', 'upload', 'delete')"
                },
                "resource_type": {
                    "bsonType": "string",
                    "description": "Type of resource affected (e.g., 'song', 'user', 'playlist')"
                },
                "resource_id": {
                    "bsonType": "string",
                    "description": "ID of the affected resource"
                },
                "details": {
                    "bsonType": ["object", "null"],
                    "description": "Additional details about the action"
                },
                "timestamp": {
                    "bsonType": "date",
                    "description": "When the action occurred"
                },
                "ip_address": {
                    "bsonType": "string",
                    "description": "IP address of the request"
                },
                "user_agent": {
                    "bsonType": "string",
                    "description": "User agent of the request"
                }
            }
        }
    }
    
    # Apply validation schemas (commented out for now as this would drop existing collections)
    """
    try:
        db.command({
            "collMod": "users",
            "validator": user_schema,
            "validationLevel": "moderate"
        })
        
        db.command({
            "collMod": "songs",
            "validator": song_schema,
            "validationLevel": "moderate"
        })
        
        db.command({
            "collMod": "playlists",
            "validator": playlist_schema,
            "validationLevel": "moderate"
        })
        
        db.command({
            "collMod": "activity_logs",
            "validator": log_schema,
            "validationLevel": "moderate"
        })
        
        logging.info("Applied validation schemas to collections")
    except Exception as e:
        logging.error(f"Error applying validation schemas: {str(e)}")
    """
    
except Exception as e:
    print(f"Error initializing database: {str(e)}")
    logging.error(f"Error initializing database: {str(e)}")