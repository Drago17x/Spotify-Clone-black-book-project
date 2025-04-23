import os
import magic
from flask import Blueprint, request, jsonify, current_app, send_from_directory, session, redirect, url_for, abort, g
from models.song import Song
from werkzeug.utils import secure_filename
import uuid
from functools import wraps

songs = Blueprint('songs', __name__)

#################################################
# Authentication Decorators
#################################################
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({"message": "Please login to access this feature"}), 401
        return f(*args, **kwargs)
    return decorated_function

#################################################
# File Type Validation
#################################################
ALLOWED_AUDIO = {'mp3', 'wav', 'ogg'}
ALLOWED_IMAGE = {'jpg', 'jpeg', 'png', 'gif'}
MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20MB max audio size
MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5MB max image size

def allowed_file(filename, allowed_extensions):
    """Check if file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def validate_file_type(file, allowed_types):
    """Validate file MIME type for security"""
    try:
        # Read the first 2048 bytes to determine file type
        file_head = file.stream.read(2048)
        file.stream.seek(0)  # Reset file pointer
        
        # Use python-magic to check MIME type
        mime = magic.Magic(mime=True)
        file_type = mime.from_buffer(file_head)
        
        # Map MIME types to extensions
        mime_types = {
            'audio': ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-wav'],
            'image': ['image/jpeg', 'image/png', 'image/gif', 'image/jpg']
        }
        
        if allowed_types == 'audio':
            return file_type in mime_types['audio']
        elif allowed_types == 'image':
            return file_type in mime_types['image']
        return False
    except Exception as e:
        print(f"Error validating file type: {str(e)}")
        return False

#################################################
# Song Upload
#################################################
@songs.route('/upload', methods=['POST'])
@login_required
def upload_song():
    try:
        # Check if user is admin
        if not session.get('is_admin', False):
            return jsonify({"message": "Only administrators can upload songs"}), 403
            
        if 'file' not in request.files:
            return jsonify({"message": "No audio file provided"}), 400
        
        audio_file = request.files['file']
        if audio_file.filename == '':
            return jsonify({"message": "No file selected"}), 400
            
        # Validate file extension
        if not allowed_file(audio_file.filename, ALLOWED_AUDIO):
            return jsonify({"message": "Invalid audio file type. Allowed types: " + ", ".join(ALLOWED_AUDIO)}), 400
            
        # Validate MIME type for enhanced security
        if not validate_file_type(audio_file, 'audio'):
            return jsonify({"message": "File content doesn't match allowed audio types"}), 400
            
        # Check file size
        audio_file.seek(0, os.SEEK_END)
        file_size = audio_file.tell()
        audio_file.seek(0)  # Reset file pointer
        
        if file_size > MAX_AUDIO_SIZE:
            max_mb = MAX_AUDIO_SIZE / (1024 * 1024)
            return jsonify({"message": f"Audio file exceeds maximum size of {max_mb}MB"}), 400

        # Get and validate form data
        title = request.form.get('title', '').strip()
        artist = request.form.get('artist', '').strip()
        mood = request.form.get('mood', '').strip()

        validation_errors = []
        if not title:
            validation_errors.append("Title is required")
        if not artist:
            validation_errors.append("Artist is required")
        if not mood:
            validation_errors.append("Mood is required")
        elif mood not in Song.MOODS:
            validation_errors.append(f"Invalid mood. Valid options: {', '.join(Song.MOODS)}")
            
        if validation_errors:
            return jsonify({"message": "Validation failed", "errors": validation_errors}), 400

        # Create unique filenames
        unique_id = str(uuid.uuid4())
        audio_filename = secure_filename(f"{unique_id}_{audio_file.filename}")
        mood_dir = f"{mood}_(mood)"
        audio_path = os.path.join(current_app.static_folder, 'songs', mood_dir, audio_filename)
        
        # Handle image file
        image_path = None
        if 'image' in request.files and request.files['image'].filename != '':
            image_file = request.files['image']
            
            # Validate image extension
            if not allowed_file(image_file.filename, ALLOWED_IMAGE):
                return jsonify({"message": "Invalid image file type. Allowed types: " + ", ".join(ALLOWED_IMAGE)}), 400
                
            # Validate image MIME type
            if not validate_file_type(image_file, 'image'):
                return jsonify({"message": "File content doesn't match allowed image types"}), 400
                
            # Check image size
            image_file.seek(0, os.SEEK_END)
            image_size = image_file.tell()
            image_file.seek(0)  # Reset file pointer
            
            if image_size > MAX_IMAGE_SIZE:
                max_mb = MAX_IMAGE_SIZE / (1024 * 1024)
                return jsonify({"message": f"Image file exceeds maximum size of {max_mb}MB"}), 400
                
            # Process image file
            image_filename = secure_filename(f"{unique_id}_{image_file.filename}")
            image_path = os.path.join(current_app.static_folder, 'songs', mood_dir, image_filename)
            
            # Create directory and save image
            try:
                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                image_file.save(image_path)
                # Store relative path for database
                image_path = os.path.join(mood_dir, image_filename)
                print(f"Successfully saved image to: {image_path}")
            except Exception as e:
                print(f"Error saving image file: {str(e)}")
                return jsonify({"message": f"Error saving image file: {str(e)}"}), 500

        # Create directory and save audio file
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        audio_file.save(audio_path)

        # Add song to database with error handling
        try:
            song_id = Song.add_song(
                title=title,
                artist=artist,
                mood=mood,
                file_path=os.path.join(mood_dir, audio_filename),
                image_path=image_path
            )
            
            return jsonify({
                "message": "Song uploaded successfully",
                "song_id": song_id
            }), 201
            
        except Exception as e:
            # Clean up files if database insert fails
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                if image_path and os.path.exists(os.path.join(current_app.static_folder, image_path)):
                    os.remove(os.path.join(current_app.static_folder, image_path))
            except Exception:
                pass  # File cleanup is best effort
                
            return jsonify({"message": f"Error adding song to database: {str(e)}"}), 500
            
    except Exception as e:
        return jsonify({"message": f"Error processing upload: {str(e)}"}), 500

#################################################
# Song Retrieval
#################################################
@songs.route('/mood/<mood>')
@login_required
def get_songs_by_mood(mood):
    # Validate mood
    if mood not in Song.MOODS:
        return jsonify({"message": f"Invalid mood. Valid options: {', '.join(Song.MOODS)}"}), 400
    
    # Parse pagination parameters
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    except ValueError:
        page = 1
        per_page = 20
        
    skip = (page - 1) * per_page
    
    # Get songs with pagination
    songs_list = Song.get_songs(mood=mood, limit=per_page, skip=skip)
    
    # Count total songs for this mood to calculate total pages
    total_count = len(Song.get_songs(mood=mood, limit=1000, skip=0))
    total_pages = (total_count + per_page - 1) // per_page
    
    return jsonify({
        "songs": songs_list,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_count,
            "total_pages": total_pages
        }
    })

@songs.route('/all')
@login_required
def get_all_songs():
    # Parse pagination parameters
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    except ValueError:
        page = 1
        per_page = 20
        
    skip = (page - 1) * per_page
    
    # Get all songs with pagination
    songs_list = Song.get_songs(limit=per_page, skip=skip)
    
    # Get total songs count
    total_count = len(Song.get_songs(limit=1000, skip=0))
    total_pages = (total_count + per_page - 1) // per_page
    
    return jsonify({
        "songs": songs_list,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_count,
            "total_pages": total_pages
        }
    })

#################################################
# Song Playback
#################################################
@songs.route('/play/<song_id>')
def play_song(song_id):
    try:
        # Check if user is logged in (optional access for previews)
        is_logged_in = session.get('user_id') is not None
        
        # Get song from database
        song = Song.get_song(song_id)
        if not song:
            print(f"Song not found with ID: {song_id}")
            return jsonify({"message": "Song not found"}), 404
        
        # Get file path and print for debugging
        file_path = song.get('file_path')
        print(f"Original file_path from database: {file_path}")
        
        if not file_path:
            return jsonify({"message": "Song file path is missing"}), 404
        
        # List of possible file paths to check
        possible_paths = [
            file_path,                                       # Original path
            file_path.lstrip('/'),                           # Without leading slash
            os.path.join('songs', file_path),                # In songs directory
            os.path.join('songs', file_path.lstrip('/')),    # In songs directory without leading slash
            os.path.join('static', 'songs', file_path),      # Full path from static/songs
            os.path.basename(file_path)                      # Just the filename itself
        ]
        
        # Find the first valid path
        valid_path = None
        valid_full_path = None
        
        for path in possible_paths:
            # Try relative to static folder
            full_path = os.path.join(current_app.static_folder, path)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                valid_path = path
                valid_full_path = full_path
                print(f"Found valid path in static folder: {valid_path}")
                break
                
            # Try absolute path
            if os.path.exists(path) and os.path.isfile(path):
                valid_path = path
                valid_full_path = path
                print(f"Found valid absolute path: {valid_path}")
                break
        
        # Also try MP3 files directly in the static/songs directory
        if not valid_path:
            base_filename = os.path.basename(file_path)
            direct_path = os.path.join(current_app.static_folder, 'songs', base_filename)
            if os.path.exists(direct_path) and os.path.isfile(direct_path):
                valid_path = os.path.join('songs', base_filename)
                valid_full_path = direct_path
                print(f"Found direct file in songs directory: {valid_path}")
        
        if not valid_path:
            print(f"No valid file path found for song {song_id}. Attempted: {possible_paths}")
            return jsonify({"message": "Song file not found on server"}), 404
        
        # Increment play count if user is logged in
        if is_logged_in:
            Song.increment_plays(song_id)
        
        # Determine MIME type based on file extension instead of using python-magic
        content_type = 'audio/mpeg'  # Default MIME type
        extension = os.path.splitext(valid_full_path)[1].lower()
        if extension == '.mp3':
            content_type = 'audio/mpeg'
        elif extension == '.wav':
            content_type = 'audio/wav'
        elif extension == '.ogg':
            content_type = 'audio/ogg'
        else:
            content_type = 'application/octet-stream'
        print(f"Using MIME type based on extension: {content_type}")
        
        # Extract directory and filename from valid path
        directory = os.path.dirname(valid_path)
        filename = os.path.basename(valid_path)
        
        print(f"Serving from directory: {directory}, filename: {filename}")
        
        # If path is in static folder, use send_from_directory
        if valid_full_path.startswith(current_app.static_folder):
            if directory:
                response = send_from_directory(
                    os.path.join(current_app.static_folder, directory),
                    filename,
                    as_attachment=False,
                    mimetype=content_type
                )
            else:
                response = send_from_directory(
                    current_app.static_folder,
                    filename,
                    as_attachment=False,
                    mimetype=content_type
                )
        else:
            # For files outside static folder, use send_file
            from flask import send_file
            response = send_file(
                valid_full_path,
                mimetype=content_type,
                as_attachment=False
            )
        
        # Set cache headers for better performance
        response.headers['Cache-Control'] = 'public, max-age=86400'  # Cache for 1 day
        response.headers['Accept-Ranges'] = 'bytes'  # Enable seek/range requests
        
        return response
        
    except Exception as e:
        import traceback
        print(f"Error playing song: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"message": f"Error playing song: {str(e)}"}), 500