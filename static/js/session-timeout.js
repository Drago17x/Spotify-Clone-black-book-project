/**
 * Session Timeout Handler
 * Monitors user activity and warns before session expiration
 */
(function() {
    // Configuration
    const sessionTimeout = 30 * 60 * 1000; // 30 minutes in milliseconds
    const warningTime = 5 * 60 * 1000;     // Show warning 5 minutes before timeout
    
    let lastActivity = Date.now();
    let warningShown = false;
    let timeoutTimer;
    
    // Session timeout warning modal
    function showTimeoutWarning() {
        if (warningShown) return;
        
        const modal = document.createElement('div');
        modal.className = 'timeout-warning-modal';
        modal.innerHTML = `
            <div class="timeout-warning-content">
                <h3>Session Timeout Warning</h3>
                <p>Your session will expire in <span id="timeout-countdown">5:00</span> minutes due to inactivity.</p>
                <button id="extend-session-btn" class="btn-green">Keep Me Signed In</button>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Add styles if not already in the page
        if (!document.getElementById('timeout-warning-styles')) {
            const style = document.createElement('style');
            style.id = 'timeout-warning-styles';
            style.textContent = `
                .timeout-warning-modal {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background-color: rgba(0, 0, 0, 0.7);
                    z-index: 9999;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .timeout-warning-content {
                    background-color: #282828;
                    border-radius: 8px;
                    padding: 24px;
                    max-width: 400px;
                    text-align: center;
                }
                .timeout-warning-content h3 {
                    color: #1DB954;
                    margin-bottom: 16px;
                }
                .timeout-warning-content p {
                    margin-bottom: 24px;
                }
                .timeout-warning-content button {
                    background-color: #1DB954;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 24px;
                    font-weight: bold;
                    cursor: pointer;
                }
                .timeout-warning-content button:hover {
                    background-color: #1ed760;
                }
            `;
            document.head.appendChild(style);
        }
        
        // Countdown timer
        const countdownEl = document.getElementById('timeout-countdown');
        let secondsLeft = warningTime / 1000;
        
        const countdownInterval = setInterval(() => {
            secondsLeft--;
            const minutes = Math.floor(secondsLeft / 60);
            const seconds = secondsLeft % 60;
            countdownEl.textContent = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
            
            if (secondsLeft <= 0) {
                clearInterval(countdownInterval);
                logout();
            }
        }, 1000);
        
        // Add event listener to extend session button
        document.getElementById('extend-session-btn').addEventListener('click', () => {
            extendSession();
            modal.remove();
            clearInterval(countdownInterval);
            warningShown = false;
        });
        
        warningShown = true;
    }
    
    // Ping server to extend session
    function extendSession() {
        lastActivity = Date.now();
        
        // Call server to extend session
        fetch('/extend-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin' // Include cookies
        }).catch(error => {
            console.error('Failed to extend session:', error);
        });
        
        resetTimeout();
    }
    
    // Logout the user when session expires
    function logout() {
        window.location.href = '/logout';
    }
    
    // Reset the timeout timer
    function resetTimeout() {
        clearTimeout(timeoutTimer);
        timeoutTimer = setTimeout(() => {
            const timeUntilExpiry = sessionTimeout - (Date.now() - lastActivity);
            
            if (timeUntilExpiry <= warningTime) {
                showTimeoutWarning();
            } else {
                resetTimeout();
            }
        }, sessionTimeout - warningTime);
    }
    
    // Activity detection events
    const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
    
    // Update last activity time when user interacts with the page
    activityEvents.forEach(event => {
        document.addEventListener(event, () => {
            lastActivity = Date.now();
            if (warningShown) {
                extendSession();
            }
        });
    });
    
    // Initialize timeout monitoring
    resetTimeout();
    
    // Check if user is logged in before starting timeout monitoring
    if (document.body.classList.contains('logged-in')) {
        console.log('Session timeout monitoring active');
    }
})(); 