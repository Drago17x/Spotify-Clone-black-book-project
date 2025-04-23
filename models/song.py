from pymongo import MongoClient
import os
import json
import shutil
import magic
from bson import ObjectId
from datetime import datetime
from config import Config




#################################################
# Database Connection
#################################################
try:
    # Check if we're using MontyDB
    if Config.MONGODB_URI.startswith("monty://"):
        from montydb import MontyClient
        client = MontyClient(Config.MONGODB_URI.replace("monty://", ""))
    else:
        from pymongo import MongoClient
        client = MongoClient(Config.MONGODB_URI,
                           serverSelectionTimeoutMS=5000,
                           connectTimeoutMS=10000,
                           socketTimeoutMS=30000)
    
    db = client[Config.DATABASE_NAME]
    songs_collection = db['songs']
    print("Connected to database for songs collection")
except Exception as e:
    print(f"Error connecting to database from song model: {e}")
    # Use a mock collection when database is not available
    class MockCollection:
        def find_one(self, *args, **kwargs):
            print("WARNING: Using mock collection. No database connection.")
            return None
            
        def find(self, *args, **kwargs):
            print("WARNING: Using mock collection. No database connection.")
            return []
            
        def insert_one(self, *args, **kwargs):
            print("WARNING: Using mock collection. No database connection.")
            class MockResult:
                @property
                def inserted_id(self):
                    return "mock_id"
            return MockResult()
            
        def update_one(self, *args, **kwargs):
            print("WARNING: Using mock collection. No database connection.")
            class MockResult:
                @property
                def matched_count(self):
                    return 0
                @property
                def modified_count(self):
                    return 0
            return MockResult()
            
        def delete_one(self, *args, **kwargs):
            print("WARNING: Using mock collection. No database connection.")
            class MockResult:
                @property
                def deleted_count(self):
                    return 0
            return MockResult()
            
        def count_documents(self, *args, **kwargs):
            print("WARNING: Using mock collection. No database connection.")
            return 0
    
    songs_collection = MockCollection()

class Song:
    MOODS = ['Happy', 'Chill', 'Energetic', 'Romantic', 'Focus', 'Angry', 'Dark', 'Bright', 'Funky', 'Love', 'Uplifting']
    
    #################################################
    # Song Creation
    #################################################
    @staticmethod
    def add_song(title, artist, mood, file_path, image_path=None):
        """
        Add a new song to the database and update the mood directory info.json
        Returns: ID of the created song or raises an exception
        """
        # Validate inputs
        if not title or not artist or not mood or not file_path:
            raise ValueError("Missing required song fields")
            
        if mood not in Song.MOODS:
            raise ValueError(f"Invalid mood. Must be one of: {', '.join(Song.MOODS)}")
            
        # Normalize paths
        file_path = file_path.replace('\\', '/')
        if file_path.startswith('/'):
            file_path = file_path.lstrip('/')
        
        if image_path:
            image_path = image_path.replace('\\', '/')
            if image_path.startswith('/'):
                image_path = image_path.lstrip('/')
        
        # Create mood directory if it doesn't exist
        mood_dir = f"{mood}_(mood)"
        song_dir = os.path.join("static", "songs", mood_dir)
        os.makedirs(song_dir, exist_ok=True)
        
        # Create song document with additional metadata
        song = {
            "title": title,
            "artist": artist,
            "mood": mood,
            "file_path": file_path,
            "image_path": image_path,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "plays": 0,
            "duration": None  # Could be populated later
        }
        
        # Update info.json in mood directory using a separate method for better separation
        try:
            Song._update_mood_info_json(mood_dir, {
                "title": title,
                "artist": artist,
                "filename": os.path.basename(file_path),
                "image": os.path.basename(image_path) if image_path else "cover.jpg"
            })
        except Exception as e:
            # If info.json update fails, log the error but continue
            print(f"Warning: Failed to update info.json for song {title}: {str(e)}")
        
        # Insert song into database
        try:
            result = songs_collection.insert_one(song)
            return str(result.inserted_id)
        except Exception as e:
            # If database insert fails, clean up the file that was uploaded
            try:
                if os.path.exists(os.path.join("static", file_path)):
                    os.remove(os.path.join("static", file_path))
                if image_path and os.path.exists(os.path.join("static", image_path)):
                    os.remove(os.path.join("static", image_path))
            except Exception:
                pass  # File cleanup is best-effort
            raise Exception(f"Failed to add song to database: {str(e)}")

    #################################################
    # Helper Methods
    #################################################
    @staticmethod
    def _update_mood_info_json(mood_dir, song_info):
        """Helper method to update the info.json file for a mood directory"""
        info_path = os.path.join("static", "songs", mood_dir, "info.json")
        
        # Create a lock file to prevent concurrent updates
        lock_path = f"{info_path}.lock"
        try:
            # Create a basic lock file
            with open(lock_path, 'w') as lock_file:
                lock_file.write(str(datetime.utcnow()))
                
            # Read existing info or create new
            try:
                with open(info_path, 'r') as f:
                    info = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                info = {"songs": []}
            
            # Add the new song and write back
            info["songs"].append(song_info)
            
            # Make a backup before writing
            if os.path.exists(info_path):
                shutil.copy2(info_path, f"{info_path}.bak")
                
            with open(info_path, 'w') as f:
                json.dump(info, f, indent=4)
                
        finally:
            # Always remove the lock file
            if os.path.exists(lock_path):
                os.remove(lock_path)

    #################################################
    # Song Retrieval
    #################################################
    @staticmethod
    def get_songs(mood=None, limit=100, skip=0):
        """
        Get songs with optional filtering by mood and pagination
        Returns: List of song objects
        """
        if mood and mood not in Song.MOODS:
            return []
            
        try:
            if mood:
                # Direct database query is more efficient for filtered results
                songs = list(songs_collection.find(
                    {"mood": mood}
                ).sort("created_at", -1).skip(skip).limit(limit))
                
                # Convert ObjectId to string
                for song in songs:
                    song['_id'] = str(song['_id'])
                    
                return songs
            
            # For all songs, get from filesystem for better compatibility with UI expectations
            base_path = os.path.join("static", "songs")
            if not os.path.exists(base_path):
                return []
                
            all_songs = []
            for mood_dir in os.listdir(base_path):
                if os.path.isdir(os.path.join(base_path, mood_dir)) and mood_dir.endswith("_(mood)"):
                    mood_name = mood_dir.replace("_(mood)", "")
                    mood_songs = Song._get_songs_by_mood(mood_name)
                    all_songs.extend(mood_songs)
            
            # Apply pagination in memory
            return all_songs[skip:skip+limit]
        except Exception as e:
            print(f"Error retrieving songs: {str(e)}")
            return []

    @staticmethod
    def _get_songs_by_mood(mood):
        """
        Helper method to get songs from a specific mood directory
        Returns: List of song objects for the mood
        """
        mood_dir = f"{mood}_(mood)"
        info_path = os.path.join("static", "songs", mood_dir, "info.json")
        
        try:
            with open(info_path, 'r') as f:
                info = json.load(f)
                songs = info.get("songs", [])
                
                # Cache song ID lookup to reduce database queries
                song_ids = {}
                db_songs = songs_collection.find({"mood": mood})
                for db_song in db_songs:
                    key = f"{db_song['title']}:{db_song['artist']}"
                    song_ids[key] = str(db_song['_id'])
                
                # Update song information
                for song in songs:
                    song['mood'] = mood
                    
                    # Use cached ID if available
                    song_key = f"{song['title']}:{song['artist']}"
                    if song_key in song_ids:
                        song['_id'] = song_ids[song_key]
                        
                    song['file_path'] = os.path.join(mood_dir, song['filename'])
                    song['image_path'] = os.path.join(mood_dir, song.get('image', 'cover.jpg'))
                
                return songs
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading mood info: {str(e)}")
            return []

    #################################################
    # Song Operations
    #################################################
    @staticmethod
    def get_song(song_id):
        """
        Get a single song by ID
        Returns: Song object or None
        """
        try:
            song = songs_collection.find_one({"_id": ObjectId(song_id)})
            if song:
                song['_id'] = str(song['_id'])
            return song
        except Exception:
            return None

    @staticmethod
    def increment_plays(song_id):
        """
        Increment play count for a song
        Returns: True if successful, False otherwise
        """
        try:
            result = songs_collection.update_one(
                {"_id": ObjectId(song_id)},
                {"$inc": {"plays": 1}}
            )
            return result.modified_count > 0
        except Exception:
            return False
            
    @staticmethod
    def delete_song(song_id):
        """
        Delete a song and its associated files
        Returns: True if successful, False otherwise
        """
        try:
            # Get song details first
            song = Song.get_song(song_id)
            if not song:
                return False
                
            # Delete database entry
            result = songs_collection.delete_one({"_id": ObjectId(song_id)})
            if result.deleted_count == 0:
                return False
                
            # Delete files from filesystem
            try:
                file_path = os.path.join("static", song['file_path'])
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
                if song.get('image_path'):
                    image_path = os.path.join("static", song['image_path'])
                    if os.path.exists(image_path):
                        os.remove(image_path)
                        
                # Update info.json to remove song
                mood_dir = f"{song['mood']}_(mood)"
                Song._remove_song_from_info_json(mood_dir, song['title'], song['artist'])
            except Exception as e:
                print(f"Warning: Failed to clean up files for song {song_id}: {str(e)}")
                
            return True
        except Exception as e:
            print(f"Error deleting song: {str(e)}")
            return False
            
    @staticmethod
    def _remove_song_from_info_json(mood_dir, title, artist):
        """Helper method to remove a song from the info.json file"""
        info_path = os.path.join("static", "songs", mood_dir, "info.json")
        if not os.path.exists(info_path):
            return
            
        try:
            with open(info_path, 'r') as f:
                info = json.load(f)
                
            # Make a backup
            shutil.copy2(info_path, f"{info_path}.bak")
            
            # Filter out the song to remove
            info["songs"] = [s for s in info["songs"] 
                           if not (s["title"] == title and s["artist"] == artist)]
            
            with open(info_path, 'w') as f:
                json.dump(info, f, indent=4)
        except Exception as e:
            print(f"Error updating info.json: {str(e)}")
            # Try to restore backup if update failed
            if os.path.exists(f"{info_path}.bak"):
                shutil.copy2(f"{info_path}.bak", info_path)