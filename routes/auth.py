from flask import jsonify, request, flash, redirect, url_for, session
from models.user import User
from email_validator import validate_email, EmailNotValidError
from functools import wraps
import time
import datetime
from bson.objectid import ObjectId

#################################################
# Rate Limiting
#################################################
# Simple in-memory rate limiting (would use Redis or similar in production)
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_TIME = 15 * 60  # 15 minutes in seconds

def is_rate_limited(ip_address):
    """Check if an IP is rate limited for login attempts"""
    now = time.time()
    
    # Clean up old entries
    for ip in list(login_attempts.keys()):
        if login_attempts[ip]['reset_time'] < now:
            del login_attempts[ip]
    
    if ip_address not in login_attempts:
        login_attempts[ip_address] = {
            'attempts': 0,
            'reset_time': now + LOCKOUT_TIME
        }
        return False
        
    # If lockout period is active
    if login_attempts[ip_address]['attempts'] >= MAX_LOGIN_ATTEMPTS:
        remaining = int(login_attempts[ip_address]['reset_time'] - now)
        if remaining > 0:
            return {'locked': True, 'remaining': remaining}
    
    return False

def record_login_attempt(ip_address, success):
    """Record a login attempt for rate limiting"""
    now = time.time()
    
    if ip_address not in login_attempts:
        login_attempts[ip_address] = {
            'attempts': 0,
            'reset_time': now + LOCKOUT_TIME
        }
    
    if success:
        # Reset on successful login
        login_attempts[ip_address]['attempts'] = 0
    else:
        # Increment attempts on failure
        login_attempts[ip_address]['attempts'] += 1
        # If max attempts reached, set lockout period
        if login_attempts[ip_address]['attempts'] >= MAX_LOGIN_ATTEMPTS:
            login_attempts[ip_address]['reset_time'] = now + LOCKOUT_TIME

#################################################
# User Registration
#################################################
def signup():
    if request.method == 'POST':
        # Get client IP for rate limiting
        ip_address = request.remote_addr
        
        # Check if rate limited (reuse login rate limiting)
        rate_limit = is_rate_limited(ip_address)
        if rate_limit and rate_limit.get('locked', False):
            minutes = int(rate_limit['remaining'] / 60)
            seconds = rate_limit['remaining'] % 60
            return jsonify({
                "message": f"Too many attempts. Please try again in {minutes}m {seconds}s."
            }), 429
        
        data = request.get_json()
        if not data:
            return jsonify({"message": "Invalid request format"}), 400
            
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')

        # Enhanced validation
        validation_errors = []
        
        if not name:
            validation_errors.append("Name is required")
        elif len(name) < 2:
            validation_errors.append("Name must be at least 2 characters")
            
        if not email:
            validation_errors.append("Email is required")
        else:
            try:
                validate_email(email, check_deliverability=False)
            except EmailNotValidError as e:
                validation_errors.append(f"Invalid email: {str(e)}")
                
        if not phone:
            validation_errors.append("Phone number is required")
        elif not (phone.isdigit() and 8 <= len(phone) <= 15):
            validation_errors.append("Phone number must contain 8-15 digits")
            
        if not password:
            validation_errors.append("Password is required")
        else:
            # Check password strength
            if len(password) < 8:
                validation_errors.append("Password must be at least 8 characters long")
            if not any(c.isupper() for c in password):
                validation_errors.append("Password must contain at least one uppercase letter")
            if not any(c.islower() for c in password):
                validation_errors.append("Password must contain at least one lowercase letter")
            if not any(c.isdigit() for c in password):
                validation_errors.append("Password must contain at least one number")
            if not any(c in "!@#$%^&*(),.?\":{}|<>" for c in password):
                validation_errors.append("Password must contain at least one special character")
            
        if password != confirm_password:
            validation_errors.append("Passwords do not match")
            
        if validation_errors:
            return jsonify({
                "message": "Validation failed",
                "errors": validation_errors
            }), 400

        # User creation is handled by model with password validation
        result = User.create_user(name, email, phone, password)
        
        # Record attempt for rate limiting (success or failure)
        record_login_attempt(ip_address, result[1] == 201)
        
        if result[1] == 201:
            flash('Account created successfully! Please log in.', 'success')
            
            # Set additional security headers
            response = result[0]
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            
            return response
        else:
            # Extract error message from the model's response
            error_data = result[0].get_json()
            error_message = error_data.get("message", "An error occurred during signup")
            
            flash('An error occurred during signup.', 'error')
            return jsonify({"message": error_message}), result[1]

#################################################
# User Authentication
#################################################
def login():
    if request.method == 'POST':
        # Get client IP for rate limiting
        ip_address = request.remote_addr
        
        # Check if rate limited
        rate_limit = is_rate_limited(ip_address)
        if rate_limit and rate_limit.get('locked', False):
            minutes = int(rate_limit['remaining'] / 60)
            seconds = rate_limit['remaining'] % 60
            return jsonify({
                "message": f"Too many failed login attempts. Please try again in {minutes}m {seconds}s.",
                "status": "rate_limited"
            }), 429
        
        # Get form data (support both JSON and form data)
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
            
        if not data:
            return jsonify({"message": "Invalid request format"}), 400
            
        email = data.get('email', '').strip()
        password = data.get('password', '')
        remember_me = data.get('remember_me', False)

        if not email or not password:
            record_login_attempt(ip_address, False)
            return jsonify({
                "message": "Email and password are required.",
                "status": "validation_error"
            }), 400

        # Authentication is handled by User model
        result = User.authenticate(email, password)
        status_code = result[1]
        
        # Record success/failure
        record_login_attempt(ip_address, status_code == 200)
        
        if status_code == 200:
            flash('Logged in successfully!', 'success')
            
            # Set session expiry based on remember_me option
            if remember_me:
                session.permanent = True
                # Permanent session lifetime is set in app.py
            else:
                # Browser session only (until browser is closed)
                session.permanent = False
            
            # Set additional security headers
            response = result[0]
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            
            return response
        elif status_code == 403:
            # Account locked status
            flash('Your account has been temporarily locked due to too many failed attempts.', 'error')
            return result
        else:
            # Handle other error cases
            flash('Invalid email or password.', 'error')
            return result