import sys
import os

# Add the project root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from flask import Blueprint, render_template, jsonify, session, redirect, url_for, current_app, request
from functools import wraps
import requests
import logging
import time
import json
from datetime import datetime
from models.user import User
from models.song import Song
from utils.song_fetcher import OpenSourceSongFetcher
from bson import ObjectId

admin = Blueprint('admin', __name__)

# Set up logging for admin actions
logger = logging.getLogger('admin_actions')
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler('logs/admin_activity.log')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

#################################################
# Authentication Decorators
#################################################
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # More comprehensive admin check
        if not session.get('user_id') or not session.get('is_admin'):
            logger.warning(f"Unauthorized admin access attempt: {request.remote_addr}")
            return redirect(url_for('login_page'))
            
        # Additional security: verify admin status from database
        try:
            user = User.get_user(session.get('user_id'))
            if not user or not user.get('is_admin'):
                logger.warning(f"User {session.get('user_id')} with invalid admin status tried to access admin area")
                session.clear()  # Clear session on suspicious activity
                return redirect(url_for('login_page'))
        except Exception as e:
            logger.error(f"Error verifying admin status: {str(e)}")
            return jsonify({"message": "Server error, please try again"}), 500
            
        # Log admin activity
        logger.info(f"Admin action: {request.endpoint} by user {session.get('user_id')} from IP {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated_function

#################################################
# Admin Dashboard
#################################################
@admin.route('/dashboard')
@admin_required
def dashboard():
    try:
        # Get all users except admin with pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        users = User.get_users(skip=(page-1)*per_page, limit=per_page, filter_query={"is_admin": False})
        
        # Get all songs grouped by mood with optimized query
        songs_by_mood = {}
        all_songs = Song.get_songs(limit=200)  # Limit to reasonable number for dashboard
        
        for song in all_songs:
            mood = song.get('mood', 'Other')
            if mood not in songs_by_mood:
                songs_by_mood[mood] = []
            songs_by_mood[mood].append(song)
            
        # Get system stats
        stats = {
            "user_count": len(users),
            "song_count": len(all_songs),
            "mood_count": len(songs_by_mood)
        }

        return render_template(
            'admin.html', 
            users=users, 
            songs_by_mood=songs_by_mood,
            stats=stats,
            current_page=page,
            items_per_page=per_page
        )
    except Exception as e:
        logger.error(f"Error in admin dashboard: {str(e)}")
        return render_template('error.html', error="An error occurred while loading the dashboard"), 500

#################################################
# User Management
#################################################
@admin.route('/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    try:
        # Make sure admin can't delete themselves
        if user_id == session.get('user_id'):
            return jsonify({"message": "Cannot delete your own admin account"}), 403
            
        # Get user before deletion for logging
        user = User.get_user(user_id)
        if not user:
            return jsonify({"message": "User not found"}), 404
            
        # Prevent deletion of other admins
        if user.get('is_admin'):
            logger.warning(f"Admin {session.get('user_id')} attempted to delete another admin: {user_id}")
            return jsonify({"message": "Cannot delete other admin accounts"}), 403
            
        # Delete user
        result = User.users_collection.delete_one({"_id": ObjectId(user_id)})
        if result.deleted_count == 0:
            return jsonify({"message": "User not found or already deleted"}), 404
            
        # Log successful deletion
        logger.info(f"Admin {session.get('user_id')} deleted user: {user_id} ({user.get('email')})")
        return jsonify({"message": "User deleted successfully"}), 200
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        return jsonify({"message": f"Error deleting user: {str(e)}"}), 500

#################################################
# Song Management
#################################################
@admin.route('/songs/<song_id>', methods=['DELETE'])
@admin_required
def delete_song(song_id):
    try:
        # Get song before deletion for logging
        song = Song.get_song(song_id)
        if not song:
            return jsonify({"message": "Song not found"}), 404
            
        # Use Song model's delete method for proper cleanup
        if Song.delete_song(song_id):
            # Log successful deletion
            logger.info(f"Admin {session.get('user_id')} deleted song: {song_id} ({song.get('title')} by {song.get('artist')})")
            return jsonify({"message": "Song deleted successfully"}), 200
        else:
            return jsonify({"message": "Song could not be deleted"}), 500
    except Exception as e:
        logger.error(f"Error deleting song {song_id}: {str(e)}")
        return jsonify({"message": f"Error deleting song: {str(e)}"}), 500

#################################################
# Open Source Song Integration
#################################################
@admin.route('/fetch-open-source-songs', methods=['POST'])
@admin_required
def fetch_open_source_songs():
    try:
        fetcher = OpenSourceSongFetcher(current_app.static_folder)
        added_songs = []
        errors = []
        
        # Get desired mood from request
        mood = request.json.get('mood', 'Chill')
        if mood not in Song.MOODS:
            return jsonify({"message": f"Invalid mood. Valid options: {', '.join(Song.MOODS)}"}), 400
            
        # Fetch songs from external API (Free Music Archive)
        try:
            # API endpoints can change, this is just an example
            api_url = "https://freemusicarchive.org/api/get/curators.json?api_key=EXAMPLE_KEY"
            
            # In reality, you would make an actual API call here
            # response = requests.get(api_url, timeout=10)
            # if response.status_code != 200:
            #     raise Exception(f"API returned status code {response.status_code}")
            # api_songs = response.json().get('songs', [])
            
            # Instead, here's a simulated API response
            api_songs = [
                {
                    "title": "Dreams",
                    "artist": "Benjamin Tissot",
                    "mood": mood,
                    "audio_url": "https://www.bensound.com/bensound-music/bensound-dreams.mp3",
                    "image_url": "https://www.bensound.com/bensound-img/dreams.jpg"
                },
                {
                    "title": "Energy",
                    "artist": "Benjamin Tissot",
                    "mood": mood,
                    "audio_url": "https://www.bensound.com/bensound-music/bensound-energy.mp3",
                    "image_url": "https://www.bensound.com/bensound-img/energy.jpg"
                },
                {
                    "title": "Happy Rock",
                    "artist": "Benjamin Tissot",
                    "mood": mood,
                    "audio_url": "https://www.bensound.com/bensound-music/bensound-happyrock.mp3",
                    "image_url": "https://www.bensound.com/bensound-img/happyrock.jpg"
                }
            ]
            
        except Exception as e:
            logger.error(f"Error fetching songs from API: {str(e)}")
            return jsonify({"message": f"Error accessing music API: {str(e)}"}), 500

        start_time = time.time()
        
        # Track progress for frontend
        total_songs = len(api_songs)
        current_song = 0
        
        # Process each song
        for song in api_songs:
            current_song += 1
            try:
                # Validate required fields
                if not all([song.get("title"), song.get("artist"), song.get("audio_url")]):
                    errors.append(f"Missing required fields for song: {song.get('title', 'Unknown')}")
                    continue
                    
                # Use the fetcher to download and add the song
                song_id = fetcher.add_public_domain_song(
                    title=song["title"],
                    artist=song["artist"],
                    mood=song["mood"],
                    audio_url=song["audio_url"],
                    image_url=song.get("image_url")
                )
                
                added_songs.append({
                    "title": song["title"],
                    "artist": song["artist"],
                    "id": song_id,
                    "mood": song["mood"]
                })
                
                # Log successful addition
                logger.info(f"Admin {session.get('user_id')} added public domain song: {song['title']} by {song['artist']}")
                
            except Exception as e:
                error_msg = f"Error adding song {song.get('title', 'Unknown')}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
                
        # Calculate processing time
        elapsed_time = time.time() - start_time

        return jsonify({
            "message": f"Added {len(added_songs)} out of {total_songs} open source songs in {elapsed_time:.2f}s",
            "songs": added_songs,
            "errors": errors if errors else None
        }), 200
        
    except Exception as e:
        logger.error(f"Error in open source song fetch: {str(e)}")
        return jsonify({"message": f"Error fetching songs: {str(e)}"}), 500