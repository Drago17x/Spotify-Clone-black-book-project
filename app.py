"""
Main application module for Spotify Clone Web Application.
"""
import os
import sys
import jwt
import atexit
import datetime
import logging
import logging.handlers
import click
from functools import wraps

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient

from config import Config
from models.user import User
from models.song import Song
from routes import auth, songs, admin

#######################################################################
# Application initialization
#######################################################################
app = Flask(__name__)

#######################################################################
# Logging Configuration
#######################################################################
# Configure application-wide logging
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

# Suppress Werkzeug (Flask's development server) logging
werkzeug_log = logging.getLogger('werkzeug')
werkzeug_log.setLevel(logging.ERROR)

# Suppress Flask development server startup messages
cli = logging.getLogger('flask.cli')
cli.setLevel(logging.ERROR)

# Setup main application logger with custom formatter
app_logger = logging.getLogger('spotify_app')
app_logger.setLevel(getattr(logging, Config.LOG_LEVEL))
file_handler = logging.FileHandler(os.path.join(log_dir, 'app.log'))
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
app_logger.addHandler(file_handler)

# Setup database logger
db_logger = logging.getLogger('database')
db_logger.setLevel(getattr(logging, Config.LOG_LEVEL))
db_handler = logging.FileHandler(os.path.join(log_dir, 'database.log'))
db_handler.setFormatter(formatter)
db_logger.addHandler(db_handler)

# Configure console output
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)
app_logger.addHandler(console_handler)
db_logger.addHandler(console_handler)

#######################################################################
# Flask Application Configuration
#######################################################################
# Configure app with Config class settings
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=7)
app.config['SESSION_COOKIE_SECURE'] = Config.SESSION_COOKIE_SECURE
app.config['SESSION_COOKIE_HTTPONLY'] = Config.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = Config.SESSION_COOKIE_SAMESITE
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH
app.config['UPLOAD_FOLDER'] = Config.UPLOAD_FOLDER

# Initialize the app with Config
Config.init_app(app)

# Apply CORS with environment-specific configuration
if Config.DEBUG:
    CORS(app, resources={r"/*": {"origins": "*", "supports_credentials": True}})
else:
    # In production, restrict CORS to specific origins
    allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'https://example.com').split(',')
    CORS(app, resources={r"/*": {"origins": allowed_origins, "supports_credentials": True}})

#######################################################################
# Database Configuration and Connection Setup
#######################################################################
try:
    # Check if we're using MontyDB (in-memory fallback)
    if Config.MONGODB_URI.startswith("monty://"):
        from montydb import MontyClient
        client = MontyClient(Config.MONGODB_URI.replace("monty://", ""))
        db = client[Config.DATABASE_NAME]
        db_logger.info(f"Connected to MontyDB in-memory database: {Config.DATABASE_NAME}")
    else:
        # Connect to MongoDB Atlas cluster with enhanced retry logic
        max_retries = 5
        retry_count = 0
        backoff_factor = 1.5
        connection_timeout = 3000
        
        connection_params = {
            "serverSelectionTimeoutMS": connection_timeout,
            "connectTimeoutMS": connection_timeout,
            "socketTimeoutMS": 30000,
            "maxPoolSize": 50,
            "minPoolSize": 5,
            "maxIdleTimeMS": 60000,
            "retryWrites": True,
            "retryReads": True,
            "w": "majority",
            "readPreference": "secondaryPreferred"
        }
        
        while retry_count < max_retries:
            try:
                db_logger.info(f"Attempting MongoDB connection (attempt {retry_count+1}/{max_retries})")
                client = MongoClient(Config.MONGODB_URI, **connection_params)
                
                # Verify connection with timeout
                client.admin.command('ping')
                db = client[Config.DATABASE_NAME]
                
                # Test accessing collections
                db.list_collection_names()
                
                db_logger.info(f"Connected to MongoDB Atlas - Database: {Config.DATABASE_NAME}")
                break
            except Exception as e:
                retry_count += 1
                error_msg = f"MongoDB connection attempt {retry_count} failed: {str(e)}"
                db_logger.error(error_msg)
                
                if retry_count >= max_retries:
                    db_logger.warning("All connection attempts failed. Switching to in-memory database.")
                    from montydb import MontyClient
                    client = MontyClient("memory")
                    db = client[Config.DATABASE_NAME]
                    db_logger.info(f"Connected to MontyDB in-memory database: {Config.DATABASE_NAME}")
                    break
                else:
                    import random
                    import time
                    wait_time = (backoff_factor ** retry_count) + random.uniform(0.1, 0.5)
                    db_logger.info(f"Retrying in {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                    connection_params["serverSelectionTimeoutMS"] *= backoff_factor
                    connection_params["connectTimeoutMS"] *= backoff_factor

    #######################################################################
    # Database Cleanup Function
    #######################################################################
    def close_mongodb_connection():
        """Close MongoDB connection when application exits"""
        if client:
            client.close()
            db_logger.info("Database connection closed")
    
    atexit.register(close_mongodb_connection)
    
except Exception as e:
    error_msg = f"Error connecting to database: {e}"
    db_logger.critical(error_msg)
    
    #######################################################################
    # Mock Client for Failed DB Connection
    #######################################################################
    class MockClient:
        def close(self):
            pass
    
    #######################################################################
    # Mock DB for Failed DB Connection
    #######################################################################
    class MockDB:
        def __getitem__(self, name):
            return {}
            
    client = MockClient()
    db = MockDB()

#######################################################################
# Request Middleware Setup
#######################################################################
@app.before_request
def before_request():
    """Middleware to perform before each request"""
    # Set the start time for request timing
    request.start_time = datetime.datetime.now()
    
    # Check for session timeout
    if session.get('user_id') and session.get('last_activity'):
        inactive_time = datetime.datetime.utcnow().timestamp() - session.get('last_activity')
        max_inactive = app.config['PERMANENT_SESSION_LIFETIME'].total_seconds()
        
        if inactive_time > max_inactive:
            app_logger.info(f"Session timeout for user {session.get('user_id')}")
            session.clear()
            return redirect(url_for('login_page'))
        
        # Reset last_activity to prevent constant session updates
        if inactive_time > 60:  # Only update every minute to reduce writes
            session['last_activity'] = datetime.datetime.utcnow().timestamp()

#######################################################################
# Response Middleware Setup
#######################################################################
@app.after_request
def after_request(response):
    """Middleware to perform after each request"""
    # Skip logging for static files
    if not request.path.startswith('/static/'):
        # Calculate response time
        if hasattr(request, 'start_time'):
            duration = datetime.datetime.now() - request.start_time
            ms = int(duration.total_seconds() * 1000)
            
            # Log request details
            app_logger.info(f"{request.method} {request.path} {response.status_code} - {ms}ms")
    
    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    return response

#######################################################################
# Template Context Processor
#######################################################################
@app.context_processor
def inject_user():
    """
    Inject user data into all templates
    This makes current_user available in all templates without explicitly passing it
    """
    current_user = None
    if session.get('user_id'):
        # Get full user data from database
        current_user = User.get_user(session.get('user_id'))
        if not current_user:
            # If user not found (maybe deleted), clear session
            session.clear()
            app_logger.warning(f"User {session.get('user_id')} not found in database, session cleared")
    
    # Return a dict of variables to make available in templates
    return {
        'current_user': current_user,
        'is_authenticated': current_user is not None,
        'is_admin': session.get('is_admin', False),
        'app_version': os.environ.get('APP_VERSION', '1.0.0')
    }

#######################################################################
# User Authentication Helper Functions
#######################################################################
def get_current_user():
    """
    Get the current logged-in user
    For use in route handlers
    
    Returns:
        dict: User object or None if not logged in
    """
    if not session.get('user_id'):
        return None
    
    user = User.get_user(session.get('user_id'))
    if not user and session.get('user_id'):
        # User was deleted or doesn't exist
        app_logger.warning(f"User {session.get('user_id')} not found in database")
        session.clear()
    
    return user

#######################################################################
# Authorization Decorators
#######################################################################
def requires_login(f):
    """
    Decorator to require login for routes
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            # Save the original destination for redirect after login
            session['next'] = request.url
            app_logger.info(f"Unauthorized access attempt to {request.path}, redirecting to login")
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def requires_admin(f):
    """
    Decorator to require admin privileges for routes
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            session['next'] = request.url
            app_logger.info(f"Unauthorized access attempt to {request.path}, redirecting to login")
            return redirect(url_for('login_page'))
        
        if not session.get('is_admin'):
            app_logger.warning(f"Non-admin user {session.get('user_id')} attempted to access admin route {request.path}")
            return render_template('error.html', error="Administrator access required"), 403
            
        return f(*args, **kwargs)
    return decorated_function

#######################################################################
# Blueprint Registration
#######################################################################
# Register authentication routes
app.route('/signup', methods=['POST'])(auth.signup)
app.route('/login', methods=['POST'])(auth.login)
# Register song-related routes
app.register_blueprint(songs.songs, url_prefix='/songs')
# Register admin routes
app.register_blueprint(admin.admin, url_prefix='/admin')

#######################################################################
# Authentication Page Routes
#######################################################################
@app.route('/signup', methods=['GET'])
def signup_page():
    """
    Render the signup page or redirect to index if already logged in
    """
    if session.get('user_id'):
        return redirect(url_for('index'))
    return render_template('signup.html')

@app.route('/login', methods=['GET'])
def login_page():
    """
    Render the login page or redirect to appropriate dashboard
    based on user role
    """
    if session.get('user_id'):
        if session.get('is_admin'):
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    """
    Log out the current user by clearing session data
    and invalidating cookies
    """
    user_id = session.get('user_id')
    if user_id:
        app_logger.info(f"User logged out: {user_id}")
    
    # Clear session and set cookie expiry
    session.clear()
    response = redirect(url_for('login_page'))
    # Additional security: expire session cookie immediately
    response.set_cookie('session', '', expires=0)
    return response

#######################################################################
# Error Handler Routes
#######################################################################
@app.errorhandler(404)
def page_not_found(e):
    """
    Handle 404 not found errors
    """
    app_logger.warning(f"404 Not Found: {request.path}")
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    """
    Handle 500 internal server errors
    """
    app_logger.error(f"500 Server Error: {str(e)}")
    return render_template('error.html', error="Internal server error"), 500

#######################################################################
# Test Data Management Routes
#######################################################################
@app.route("/add-test-songs", methods=['GET', 'POST'])
def add_test_songs():
    """
    Add test songs to the database for demonstration purposes
    """
    if request.method == 'POST':
        try:
            # Sample test songs data
            test_songs = [
                {
                    "title": "Summer Vibes", 
                    "artist": "Beach Waves",
                    "mood": "Happy",
                    "file_path": "Happy_(mood)/sample_happy_1.mp3"
                },
                {
                    "title": "Rainy Day",
                    "artist": "Cloud Nine",
                    "mood": "Sad",
                    "file_path": "Sad_(mood)/sample_sad_1.mp3"
                },
                {
                    "title": "Workout Mix",
                    "artist": "Fitness Kings",
                    "mood": "Energetic",
                    "file_path": "Energetic_(mood)/sample_energetic_1.mp3"
                },
                {
                    "title": "Study Session",
                    "artist": "Focus Masters",
                    "mood": "Calm",
                    "file_path": "Calm_(mood)/sample_calm_1.mp3"
                },
                {
                    "title": "Night Drive",
                    "artist": "Midnight Cruisers",
                    "mood": "Relaxed",
                    "file_path": "Relaxed_(mood)/sample_relaxed_1.mp3"
                },
                {
                    "title": "Epic Battle",
                    "artist": "Warriors",
                    "mood": "Angry",
                    "file_path": "Angry_(mood)/sample_angry_1.mp3"
                }
            ]
            
            # Add each test song to the database
            added_songs = []
            for song_data in test_songs:
                song_id = Song.add_song(
                    title=song_data["title"],
                    artist=song_data["artist"],
                    mood=song_data["mood"],
                    file_path=song_data["file_path"],
                    image_path=None
                )
                added_songs.append({"id": song_id, "title": song_data["title"]})
            
            app_logger.info(f"Added {len(added_songs)} test songs")
            return jsonify({
                "message": "Test songs added successfully",
                "songs": added_songs
            }), 201
            
        except Exception as e:
            app_logger.error(f"Error adding test songs: {str(e)}")
            return jsonify({"message": f"Error adding test songs: {str(e)}"}), 500
    
    # GET request renders a simple form
    return render_template("add_test_songs.html")

#######################################################################
# Homepage Route
#######################################################################
@app.route("/")
def index():
    """
    Main application route - renders homepage with songs grouped by mood
    and personalized greeting based on time of day.
    This route is accessible without login.
    """
    user = None
    is_admin = False
    
    if session.get('user_id'):
        # Get user data if logged in
        user = User.get_user(session.get('user_id'))
        is_admin = session.get('is_admin', False)
        if user and is_admin:
            return redirect(url_for('admin.dashboard'))

    # Get all songs using the Song model
    all_songs = Song.get_songs()
    songs_by_mood = {}
    
    # Group songs by mood using dictionary comprehension
    for song in all_songs:
        mood = song.get('mood', 'Other')
        if mood not in songs_by_mood:
            songs_by_mood[mood] = []
        
        # Set default cover image if none exists
        if not song.get('image_path') or song.get('image_path') == 'None' or song.get('image_path') is None:
            song['image_path'] = 'img/default-cover.jpg'
        
        # Limit songs for non-logged in users
        song_limit = 6 if not user else float('inf')
        if len(songs_by_mood[mood]) < song_limit:
            songs_by_mood[mood].append(song)
    
    # Determine time of day for greeting
    current_hour = datetime.datetime.now().hour
    time_periods = {
        (5, 12): 'morning',
        (12, 17): 'afternoon',
        (17, 24): 'evening',
        (0, 5): 'night'
    }
    
    time_of_day = next((period for (start, end), period in time_periods.items() 
                      if start <= current_hour < end), 'day')
    
    # Render the template with context data
    return render_template(
        "index.html",
        songs_by_mood=songs_by_mood,
        user=user,
        is_admin=is_admin,
        time_of_day=time_of_day
    )

#######################################################################
# Search Functionality
#######################################################################
@app.route("/search")
def search():
    """
    Search for songs by title, artist, or mood.
    This route handles search queries and returns matching results.
    """
    query = request.args.get('q', '').strip()
    user = None
    is_admin = False
    
    if session.get('user_id'):
        # Get user data if logged in
        user = User.get_user(session.get('user_id'))
        is_admin = session.get('is_admin', False)
    
    # If query is empty, redirect to home page
    if not query:
        return redirect(url_for('index'))
    
    search_results = []
    try:
        # Create a search query for MongoDB using case-insensitive regex
        search_criteria = {
            '$or': [
                {'title': {'$regex': query, '$options': 'i'}},
                {'artist': {'$regex': query, '$options': 'i'}},
                {'mood': {'$regex': query, '$options': 'i'}}
            ]
        }
        
        # Execute the search query
        search_results = list(Song.collection().find(search_criteria))
        
        # Set default cover image if none exists
        for song in search_results:
            if not song.get('image_path') or song.get('image_path') == 'None' or song.get('image_path') is None:
                song['image_path'] = 'img/default-cover.jpg'
        
        # Limit results for non-logged-in users
        if not user:
            search_results = search_results[:12]
        
        app_logger.info(f"Search for '{query}' returned {len(search_results)} results")
            
    except Exception as e:
        app_logger.error(f"Search error: {str(e)}")
        # If search fails, return empty results
        search_results = []
    
    return render_template(
        "search_results.html",
        query=query,
        results=search_results,
        result_count=len(search_results),
        user=user,
        is_admin=is_admin
    )

#######################################################################
# Session Management
#######################################################################
@app.route('/extend-session', methods=['POST'])
def extend_session():
    """
    Endpoint to extend the user's session when they're active
    """
    if session.get('user_id'):
        session['last_activity'] = datetime.datetime.utcnow().timestamp()
        return jsonify({"message": "Session extended"}), 200
    return jsonify({"message": "No active session"}), 401

#######################################################################
# Health Check API
#######################################################################
@app.route('/health')
def health_check():
    """
    Simple health check endpoint for monitoring
    """
    try:
        # Test database connectivity
        db.command('ping')
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    
    return jsonify({
        "status": "ok",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "database": db_status,
        "version": os.environ.get('APP_VERSION', '1.0.0')
    })

#######################################################################
# User Profile Routes
#######################################################################
@app.route('/profile')
@requires_login
def user_profile():
    """
    User profile page - demonstrates proper use of user context
    This route requires login (uses the @requires_login decorator)
    """
    # Get current user data - no need to pass to template as it's injected by context processor
    user = get_current_user()
    app_logger.info(f"User {user['_id']} viewing profile")
    
    # Get user's recently played songs (last 10)
    # In a real app, you would track play history; here we'll just get random songs
    recent_songs = Song.get_songs(limit=10)
    
    # Render template with user data
    return render_template(
        "profile.html",
        recent_songs=recent_songs
    )

#######################################################################
# Debug Route for Song Playback
#######################################################################
@app.route("/debug-song/<song_id>")
def debug_song(song_id):
    """
    Debug route to test song playback and file paths
    """
    try:
        # Get song from database
        song = Song.get_song(song_id)
        if not song:
            return jsonify({"message": "Song not found", "id": song_id}), 404
            
        # Get file path
        file_path = song.get('file_path')
        app_logger.info(f"DEBUG: Original file_path from database: {file_path}")
        
        if not file_path:
            return jsonify({"message": "Song file path is missing"}), 404
            
        # Check if file exists in static folder
        static_path = os.path.join(app.static_folder, file_path)
        exists_in_static = os.path.exists(static_path)
        
        # Check if file exists in songs folder
        songs_path = os.path.join(app.static_folder, 'songs', file_path)
        exists_in_songs = os.path.exists(songs_path)
        
        # Check for the file directly in static/songs
        direct_path = os.path.join(app.static_folder, 'songs', os.path.basename(file_path))
        exists_direct = os.path.exists(direct_path)
        
        # List all MP3 files in static/songs
        song_files = []
        for root, dirs, files in os.walk(os.path.join(app.static_folder, 'songs')):
            for file in files:
                if file.endswith('.mp3'):
                    rel_path = os.path.relpath(os.path.join(root, file), app.static_folder)
                    song_files.append(rel_path)
        
        return jsonify({
            "song_id": song_id,
            "song_data": song,
            "file_path": file_path,
            "static_path": static_path,
            "exists_in_static": exists_in_static,
            "songs_path": songs_path,
            "exists_in_songs": exists_in_songs,
            "direct_path": direct_path,
            "exists_direct": exists_direct,
            "mp3_files_found": song_files[:10],  # Limit to 10 files
            "static_folder": app.static_folder
        })
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        app_logger.error(f"Debug song error: {str(e)}\n{error_details}")
        return jsonify({"message": f"Error: {str(e)}", "traceback": error_details}), 500

#######################################################################
# Direct Song File Route
#######################################################################
@app.route("/direct-song/<path:filename>")
def direct_song_file(filename):
    """
    Direct file access route for debugging song playback issues
    """
    app_logger.info(f"DEBUG: Attempting to serve file directly: {filename}")
    try:
        # Try to find the file in various locations
        # 1. Try direct static folder
        if os.path.exists(os.path.join(app.static_folder, filename)):
            app_logger.info(f"DEBUG: Serving from static folder: {filename}")
            return send_from_directory(app.static_folder, filename)
            
        # 2. Try in static/songs folder
        songs_path = os.path.join('songs', filename)
        if os.path.exists(os.path.join(app.static_folder, songs_path)):
            app_logger.info(f"DEBUG: Serving from static/songs folder: {songs_path}")
            return send_from_directory(app.static_folder, songs_path)
            
        # 3. Try just the filename in static/songs
        base_filename = os.path.basename(filename)
        base_path = os.path.join('songs', base_filename)
        if os.path.exists(os.path.join(app.static_folder, base_path)):
            app_logger.info(f"DEBUG: Serving from static/songs with basename: {base_path}")
            return send_from_directory(os.path.join(app.static_folder, 'songs'), base_filename)
            
        app_logger.error(f"DEBUG: File not found in any location: {filename}")
        return jsonify({"message": "File not found"}), 404
        
    except Exception as e:
        app_logger.error(f"DEBUG: Error serving file: {str(e)}")
        return jsonify({"message": f"Error: {str(e)}"}), 500

#######################################################################
# Application Entry Point
#######################################################################
if __name__ == '__main__':
    # Create upload directory for songs if it doesn't exist
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    # Create directory for song mood categories
    for mood in ['Happy', 'Sad', 'Energetic', 'Calm', 'Relaxed', 'Angry', 'Dark', 'Bright', 'Funky', 'Love', 'Uplifting']:
        os.makedirs(os.path.join(Config.UPLOAD_FOLDER, f"{mood}_(mood)"), exist_ok=True)
    
    # Ensure admin user exists
    User.create_admin_if_not_exists()
    
    # Disable Flask's default startup messages
    click.echo = lambda *args, **kwargs: None
    
    # Print startup message to console
    print("\n" + "=" * 70)
    print(f"  Spotify Clone Application")
    print(f"  Environment: {'Development' if Config.DEBUG else 'Production'}")
    print(f"  Server URL:  http://{Config.HOST}:{Config.PORT}")
    print(f"  Database:    {Config.DATABASE_NAME}")
    print("=" * 70)
    print("  Press CTRL+C to quit\n")
    
    # Start the Flask application
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        use_reloader=Config.DEBUG,
        threaded=True
    )