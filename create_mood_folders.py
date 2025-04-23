import os
import json

# Define all mood folders
MOODS = ['Happy', 'Chill', 'Energetic', 'Romantic', 'Focus', 'Angry', 'Dark', 'Bright', 'Funky', 'Love', 'Uplifting', 'Sad', 'Relaxed', 'Calm']

# Base directory for songs
SONGS_DIR = os.path.join('static', 'songs')

def create_mood_folder_structure():
    """Create mood folders with info.json files"""
    print("Creating mood folder structure...")
    
    # Make sure the base songs directory exists
    os.makedirs(SONGS_DIR, exist_ok=True)
    
    # Create each mood folder and info.json
    for mood in MOODS:
        mood_dir = os.path.join(SONGS_DIR, f"{mood}_(mood)")
        os.makedirs(mood_dir, exist_ok=True)
        
        info_path = os.path.join(mood_dir, 'info.json')
        if not os.path.exists(info_path):
            # Create a default info.json file
            info = {
                "mood": mood,
                "description": f"{mood} songs and tracks",
                "songs": []
            }
            
            with open(info_path, 'w') as f:
                json.dump(info, f, indent=4)
            
            print(f"Created {mood} folder with info.json")
        else:
            print(f"{mood} folder already exists")

    print("Mood folder structure created successfully")

if __name__ == "__main__":
    create_mood_folder_structure() 