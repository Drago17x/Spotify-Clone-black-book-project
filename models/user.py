from flask import jsonify, session, current_app
from pymongo import MongoClient
import bcrypt
import jwt
import datetime
import re
import os
import logging
from bson.objectid import ObjectId
from config import Config
from email_validator import validate_email, EmailNotValidError

#################################################
# Logging Configuration
#################################################
# Setup user model logger
user_logger = logging.getLogger('user_model')
user_logger.setLevel(logging.INFO)
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)
handler = logging.FileHandler(os.path.join(log_dir, 'user.log'))
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
user_logger.addHandler(handler)

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
    users_collection = db['users']
    user_logger.info("Connected to database for users collection")
except Exception as e:
    user_logger.error(f"Error connecting to database from user model: {e}")
    # Use a mock collection when database is not available
    class MockCollection:
        def find_one(self, *args, **kwargs):
            user_logger.warning("Using mock collection. No database connection.")
            return None
            
        def find(self, *args, **kwargs):
            user_logger.warning("Using mock collection. No database connection.")
            return []
            
        def insert_one(self, *args, **kwargs):
            user_logger.warning("Using mock collection. No database connection.")
            class MockResult:
                @property
                def inserted_id(self):
                    return "mock_id"
            return MockResult()
            
        def update_one(self, *args, **kwargs):
            user_logger.warning("Using mock collection. No database connection.")
            class MockResult:
                @property
                def matched_count(self):
                    return 0
            return MockResult()
            
        def delete_one(self, *args, **kwargs):
            user_logger.warning("Using mock collection. No database connection.")
            return None
            
        def count_documents(self, *args, **kwargs):
            user_logger.warning("Using mock collection. No database connection.")
            return 0
    
    users_collection = MockCollection()

class User:
    users_collection = users_collection  # Expose collection as class variable
    
    #################################################
    # User Creation
    #################################################
    @staticmethod
    def create_user(name, email, phone, password, is_admin=False, set_session=True):
        """
        Create a new user with the given details
        
        Args:
            name: User's full name
            email: User's email address (will be validated)
            phone: User's phone number
            password: User's password (will be validated and hashed)
            is_admin: Whether the user should have admin privileges
            set_session: Whether to set session data (not used during startup)
            
        Returns:
            tuple: (jsonify response, status code)
        """
        # Validate email format
        try:
            validated_email = validate_email(email, check_deliverability=False)
            email = validated_email.normalized
        except EmailNotValidError as e:
            user_logger.warning(f"Invalid email during user creation: {email} - {str(e)}")
            return jsonify({"message": f"Invalid email: {str(e)}"}), 400

        # Check if email already exists
        if users_collection.find_one({"email": email}):
            user_logger.warning(f"Attempted to create user with existing email: {email}")
            return jsonify({"message": "Email already exists"}), 400

        # Validate password strength
        password_validation = User._validate_password(password)
        if password_validation is not True:
            user_logger.warning(f"Weak password used during account creation for {email}")
            return jsonify({
                "message": "Password doesn't meet security requirements", 
                "errors": password_validation
            }), 400

        # Hash password with better work factor
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(12))
        
        # Create user document with additional metadata
        user = {
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed,
            "is_admin": is_admin,
            "created_at": datetime.datetime.utcnow(),
            "last_login": None
        }
        
        try:
            result = users_collection.insert_one(user)
            user_id = str(result.inserted_id)
            user['_id'] = user_id
            del user['password']  # Remove password before returning to client
            
            # Only set session if we're in a request context
            if set_session:
                try:
                    session['user_id'] = user_id
                    session['is_admin'] = is_admin
                    session['last_activity'] = datetime.datetime.utcnow().timestamp()
                except RuntimeError:
                    # Working outside of request context, session not available
                    user_logger.info(f"Created user {user_id} outside request context")
            
            user_logger.info(f"User created successfully: {user_id} (admin: {is_admin})")
            return jsonify({"message": "User created successfully", "user": user}), 201
        except Exception as e:
            user_logger.error(f"Database error during user creation: {str(e)}")
            return jsonify({"message": f"Database error: {str(e)}"}), 500

    #################################################
    # Password Validation
    #################################################
    @staticmethod
    def _validate_password(password):
        """
        Validate password strength:
        - At least 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        
        Returns either True or a specific error message
        """
        errors = []
        
        if len(password) < 8:
            errors.append("Password must be at least 8 characters")
            
        # Check for uppercase, lowercase, digit, and special character
        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
            
        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
            
        if not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
            
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
            
        if errors:
            return errors
            
        return True

    #################################################
    # User Authentication
    #################################################
    @staticmethod
    def authenticate(email, password):
        """
        Authenticate a user with email and password
        Returns user data and session information on success
        """
        if not email or not password:
            user_logger.warning("Login attempt with missing email or password")
            return jsonify({"message": "Email and password are required"}), 400
            
        # Find user by email
        user = users_collection.find_one({"email": email})
        if not user:
            # Don't reveal if email exists or not for security
            user_logger.warning(f"Login attempt with non-existent email: {email}")
            return jsonify({"message": "Invalid credentials"}), 401

        # Check if account is locked
        if user.get('account_locked', False):
            if user.get('lock_expires_at', datetime.datetime.now()) > datetime.datetime.now():
                minutes_remaining = int((user['lock_expires_at'] - datetime.datetime.now()).total_seconds() / 60)
                user_logger.warning(f"Login attempt on locked account: {email}")
                return jsonify({"message": f"Account is temporarily locked. Please try again in {minutes_remaining} minutes."}), 403
            else:
                # Unlock account if lock has expired
                users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"account_locked": False, "login_attempts": 0}}
                )
                user_logger.info(f"Account lock expired for {email}")

        # Use constant-time comparison to prevent timing attacks
        try:
            if bcrypt.checkpw(password.encode('utf-8'), user['password']):
                # Reset failed login attempts
                users_collection.update_one(
                    {"_id": user["_id"]},
                    {
                        "$set": {
                            "last_login": datetime.datetime.utcnow(),
                            "login_attempts": 0
                        }
                    }
                )
                
                # Set user session data
                user_id = str(user['_id'])
                is_admin = user.get('is_admin', False)
                session['user_id'] = user_id
                session['is_admin'] = is_admin
                session['name'] = user.get('name', '')
                session['email'] = user.get('email', '')
                session['last_activity'] = datetime.datetime.utcnow().timestamp()
                session.permanent = True  # Use permanent session with configured lifetime
                
                # Prepare user data to return (excluding sensitive fields)
                user_data = {
                    "name": user['name'],
                    "email": user['email'],
                    "phone": user.get('phone', ''),
                    "_id": user_id,
                    "is_admin": is_admin,
                    "last_login": user.get('last_login')
                }
                
                user_logger.info(f"Successful login: {user_id} (admin: {is_admin})")
                return jsonify({
                    "message": "Login successful",
                    "user": user_data,
                    "redirect": "/admin/dashboard" if is_admin else "/"
                }), 200
            
            # If we get here, password is incorrect    
            # Increment failed login attempts
            login_attempts = user.get('login_attempts', 0) + 1
            update_data = {"login_attempts": login_attempts}
            
            # Lock account after 5 failed attempts
            if login_attempts >= 5:
                lock_duration = datetime.timedelta(minutes=15)
                lock_expires_at = datetime.datetime.now() + lock_duration
                update_data.update({
                    "account_locked": True,
                    "lock_expires_at": lock_expires_at
                })
                
            users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": update_data}
            )
            
            if login_attempts >= 5:
                user_logger.warning(f"Account locked after 5 failed attempts: {email}")
                return jsonify({"message": "Too many failed login attempts. Account locked for 15 minutes."}), 403
                
            user_logger.warning(f"Failed login attempt for {email} (attempt #{login_attempts})")
            return jsonify({"message": "Invalid credentials"}), 401
        except Exception as e:
            user_logger.error(f"Authentication error: {str(e)}")
            return jsonify({"message": "Authentication error"}), 500

    #################################################
    # User Retrieval
    #################################################
    @staticmethod
    def get_user(user_id):
        """
        Get a user by ID with sensitive fields removed
        
        Args:
            user_id: The ID of the user to retrieve
            
        Returns:
            dict: User object or None if not found
        """
        try:
            user = users_collection.find_one({"_id": ObjectId(user_id)})
            if user:
                user['_id'] = str(user['_id'])
                # Don't send password to client
                if 'password' in user:
                    del user['password']
                return user
            return None
        except Exception as e:
            user_logger.error(f"Error getting user {user_id}: {str(e)}")
            return None
            
    @staticmethod
    def get_users(skip=0, limit=20, filter_query=None):
        """
        Get a paginated list of users with optional filtering
        
        Args:
            skip: Number of records to skip (pagination offset)
            limit: Maximum number of records to return
            filter_query: Optional MongoDB query to filter users
            
        Returns:
            list: List of user objects
        """
        query = filter_query or {}
        
        try:
            users = list(users_collection.find(query).skip(skip).limit(limit))
            for user in users:
                user['_id'] = str(user['_id'])
                if 'password' in user:
                    del user['password']
            return users
        except Exception as e:
            user_logger.error(f"Error getting users: {str(e)}")
            return []

    #################################################
    # User Management
    #################################################
    @staticmethod
    def update_user(user_id, update_data):
        """
        Update user details
        
        Args:
            user_id: The ID of the user to update
            update_data: Dictionary of fields to update
            
        Returns:
            tuple: (jsonify response, status code)
        """
        # Don't allow updating email to an existing one
        if 'email' in update_data:
            try:
                validated_email = validate_email(update_data['email'], check_deliverability=False)
                update_data['email'] = validated_email.normalized
                
                existing = users_collection.find_one({
                    "email": update_data['email'],
                    "_id": {"$ne": ObjectId(user_id)}
                })
                if existing:
                    user_logger.warning(f"Attempted to update user {user_id} to existing email: {update_data['email']}")
                    return jsonify({"message": "Email already in use"}), 400
            except EmailNotValidError:
                user_logger.warning(f"Attempted to update user {user_id} with invalid email: {update_data['email']}")
                return jsonify({"message": "Invalid email format"}), 400
                
        # Handle password updates separately with hashing
        if 'password' in update_data:
            password_validation = User._validate_password(update_data['password'])
            if password_validation is not True:
                user_logger.warning(f"Weak password used during password update for user {user_id}")
                return jsonify({"message": "Password doesn't meet security requirements", "errors": password_validation}), 400
                
            update_data['password'] = bcrypt.hashpw(
                update_data['password'].encode('utf-8'), 
                bcrypt.gensalt(12)
            )
        
        # Add updated_at timestamp
        update_data['updated_at'] = datetime.datetime.utcnow()
        
        try:
            result = users_collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                user_logger.warning(f"Attempted to update non-existent user: {user_id}")
                return jsonify({"message": "User not found"}), 404
            
            user_logger.info(f"User updated successfully: {user_id}")    
            return jsonify({"message": "User updated successfully"}), 200
        except Exception as e:
            user_logger.error(f"Error updating user {user_id}: {str(e)}")
            return jsonify({"message": f"Error updating user: {str(e)}"}), 500

    #################################################
    # Admin User Management
    #################################################
    @staticmethod
    def create_admin_if_not_exists():
        """
        Create an admin user if one doesn't exist
        
        Returns:
            bool: True if admin was created or already exists, False if failed
        """
        admin_exists = users_collection.find_one({"is_admin": True})
        if not admin_exists:
            user_logger.info("Admin user doesn't exist - creating default admin")
            try:
                User.create_user(
                    name="Admin",
                    email="admin@spotify.com",
                    phone="1234567890",
                    password="Admin@123",
                    is_admin=True,
                    set_session=False  # Don't try to set session during app startup
                )
                user_logger.info("Admin user created successfully")
                return True
            except Exception as e:
                user_logger.error(f"Error creating admin user: {str(e)}")
                return False
        else:
            user_logger.info("Admin user already exists")
            return True