import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection settings
MONGODB_URI = os.environ.get('MONGO_URI')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'spotify_clone')

# If MongoDB URI is not set or invalid, use a fallback in-memory option
if not MONGODB_URI:
    print("WARNING: No MongoDB URI found. Using in-memory database.")
    # Using MontyDB as a fallback (MongoDB-compatible in-memory database)
    MONGODB_URI = "monty://memory"
    # You'll need to install montydb: pip install montydb
    # It's a pure Python MongoDB implementation that works in-memory

# Print values for debugging
