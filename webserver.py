from flask import Flask, jsonify, render_template, request
from threading import Thread
import logging
import time
from lap_timer import LapTimer

class WebServer:
    """
    Professional Flask web server for pumptrack lap timer.
    Provides real-time race monitoring and control via web interface.
    """

    def __init__(self, config: dict):
        """Initialize the Flask web server with comprehensive configuration."""
        self.app = Flask(__name__)
        self.config = config
        
        # Configuration with validation
        web_config = config.get('web_server', {})
        self.host = web_config.get('host', '0.0.0.0')
        self.port = int(web_config.get('port', 5000))
        self.debug = bool(web_config.get('debug', False))
        
        # Validate configuration
        if not (1024 <= self.port <= 65535):
            raise ValueError(f"Invalid port {self.port}. Must be 1024-65535")
            
        if self.debug and self.host != '127.0.0.1':
            logging.warning("Debug mode with non-localhost host - potential security risk!")
        
        # Thread management
        self.thread = None
        self.running = False

        # Configure Flask
        self.app.config.update({
            'TEMPLATES_AUTO_RELOAD': True,
            'JSON_SORT_KEYS': False,
            'JSONIFY_PRETTYPRINT_REGULAR': self.debug
        })
        
        # Setup routes and middleware
        self._setup_routes()
        self._setup_middleware()
        self._setup_error_handlers()

        logging.info(f"WebServer initialized: http://{self.host}:{self.port} (debug={self.debug})")

    def _setup_routes(self):
        """Setup all Flask routes."""
        self.app.route('/')(self.index)
        self.app.route('/health')(self.health_check)
        self.app.route('/api/status')(self.api_status)
        self.app.route('/api/start', methods=['POST'])(self.api_start_race)
        self.app.route('/api/stop', methods=['POST'])(self.api_stop_race)
        self.app.route('/api/reset', methods=['POST'])(self.api_manual_reset)
        self.app.route('/api/statistics')(self.api_statistics)

    def _setup_middleware(self):
        """Setup request/response middleware."""
        @self.app.before_request
        def log_request():
            if self.debug:
                logging.debug(f"Request: {request.method} {request.path} from {request.remote_addr}")

        @self.app.after_request
        def add_headers(response):
            # Add CORS headers
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            
            # Add cache control for API endpoints
            if request.path.startswith('/api/'):
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
            
            if self.debug:
                logging.debug(f"Response: {response.status_code} for {request.path}")
            return response

    def _setup_error_handlers(self):
        """Setup error handlers."""
        self.app.errorhandler(404)(self.not_found)
        self.app.errorhandler(500)(self.internal_error)
        self.app.errorhandler(Exception)(self.handle_exception)

    def index(self):
        """Render the main HTML page with race status and statistics."""
        try:
            timer = LapTimer.get_instance()
            if timer is None:
                return render_template('error.html', 
                                     message="LapTimer not initialized",
                                     suggestion="Please start the race system first.")
            
            status = timer.get_status()
            lap_results = timer.get_lap_results()
            stats = timer.get_race_statistics()
            
            return render_template('base.html', 
                                 status=status, 
                                 lap_results=lap_results, 
                                 stats=stats)
        except Exception as e:
            logging.error(f"Error in index route: {e}")
            return render_template('error.html', 
                                 message="System error occurred",
                                 suggestion="Please check the logs and restart if needed.")

    def api_status(self):
        """Return JSON status and statistics for dynamic updates."""
        try:
            timer = LapTimer.get_instance()
            if timer is None:
                return jsonify({'error': 'LapTimer not initialized'}), 500
            
            status = timer.get_status()
            status['statistics'] = timer.get_race_statistics()
            status['timestamp'] = time.time()
            
            return jsonify(status)
        except Exception as e:
            logging.error(f"Error in API status: {e}")
            return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

    def api_start_race(self):
        """Start a new race."""
        try:
            timer = LapTimer.get_instance()
            if timer is None:
                return jsonify({'success': False, 'message': 'LapTimer not initialized'}), 500
            
            if timer.start_race():
                logging.info("Race started via web interface")
                return jsonify({'success': True, 'message': 'Race started successfully'})
            else:
                return jsonify({'success': False, 'message': 'Failed to start race - check LIDAR connection'}), 400
        except Exception as e:
            logging.error(f"Error starting race via web: {e}")
            return jsonify({'success': False, 'message': f'Error starting race: {str(e)}'}), 500

    def api_stop_race(self):
        """Stop the current race."""
        try:
            timer = LapTimer.get_instance()
            if timer is None:
                return jsonify({'success': False, 'message': 'LapTimer not initialized'}), 500
            
            timer.stop_race()
            logging.info("Race stopped via web interface")
            return jsonify({'success': True, 'message': 'Race stopped successfully'})
        except Exception as e:
            logging.error(f"Error stopping race via web: {e}")
            return jsonify({'success': False, 'message': f'Error stopping race: {str(e)}'}), 500

    def api_manual_reset(self):
        """Manually reset current lap."""
        try:
            timer = LapTimer.get_instance()
            if timer is None:
                return jsonify({'success': False, 'message': 'LapTimer not initialized'}), 500
            
            if hasattr(timer, 'manual_reset') and timer.manual_reset():
                logging.info("Lap manually reset via web interface")
                return jsonify({'success': True, 'message': 'Lap manually reset'})
            else:
                return jsonify({'success': False, 'message': 'No active lap to reset'}), 400
        except Exception as e:
            logging.error(f"Error in manual reset via web: {e}")
            return jsonify({'success': False, 'message': f'Error resetting lap: {str(e)}'}), 500

    def api_statistics(self):
        """Return detailed race statistics."""
        try:
            timer = LapTimer.get_instance()
            if timer is None:
                return jsonify({'error': 'LapTimer not initialized'}), 500
            
            stats = timer.get_race_statistics()
            lap_times = timer.get_lap_times()
            lap_results = timer.get_lap_results()
            status = timer.get_status()
            
            return jsonify({
                'statistics': stats,
                'lap_times': lap_times,
                'lap_results': lap_results,
                'status': status,
                'timestamp': time.time()
            })
        except Exception as e:
            logging.error(f"Error getting statistics via web: {e}")
            return jsonify({'error': f'Failed to get statistics: {str(e)}'}), 500

    def health_check(self):
        """System health check endpoint."""
        try:
            timer = LapTimer.get_instance()
            timer_status = timer.get_status() if timer else {}
            
            health = {
                'status': 'healthy',
                'timestamp': time.time(),
                'services': {
                    'lap_timer': timer is not None,
                    'web_server': self.is_running(),
                    'lidar_healthy': timer_status.get('lidar_healthy', False),
                    'race_running': timer_status.get('running', False)
                },
                'version': '1.0.0'
            }
            
            # Overall health check
            if not all(health['services'].values()):
                health['status'] = 'degraded'
                return jsonify(health), 206  # Partial Content
                
            return jsonify(health)
            
        except Exception as e:
            logging.error(f"Health check failed: {e}")
            return jsonify({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': time.time()
            }), 500

    def not_found(self, error):
        """404 error handler."""
        return render_template('error.html', 
                             message="Page not found",
                             suggestion="Please check the URL and try again."), 404

    def internal_error(self, error):
        """500 error handler."""
        logging.error(f"Internal server error: {error}")
        return render_template('error.html', 
                             message="Internal server error",
                             suggestion="Please try again in a moment."), 500

    def handle_exception(self, e):
        """Handle unexpected exceptions."""
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        return render_template('error.html', 
                             message="An unexpected error occurred",
                             suggestion="Please try again or contact support."), 500

    def start(self):
        """Start the Flask server in a separate thread."""
        if not self.running:
            self.running = True
            self.thread = Thread(target=self._run_server, daemon=True)
            self.thread.start()
            logging.info(f"WebServer started at http://{self.host}:{self.port}")
            return True
        return False

    def _run_server(self):
        """Internal method to run Flask server with error handling."""
        try:
            self.app.run(
                host=self.host,
                port=self.port,
                debug=self.debug,
                use_reloader=False,
                threaded=True  # Enable threading for concurrent requests
            )
        except Exception as e:
            logging.error(f"Flask server error: {e}")
            self.running = False

    def stop(self):
        """Stop the Flask server."""
        if self.running:
            self.running = False
            logging.info("WebServer stopped")

    def is_running(self) -> bool:
        """Check if web server is running."""
        return bool(self.running and self.thread is not None and self.thread.is_alive())

    def get_url(self) -> str:
        """Get the server URL."""
        return f"http://{self.host}:{self.port}"

    def cleanup(self):
        """Cleanup web server resources."""
        self.stop()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        logging.info("WebServer cleaned up")

    def get_stats(self) -> dict:
        """Get web server statistics."""
        return {
            'host': self.host,
            'port': self.port,
            'running': self.is_running(),
            'debug': self.debug,
            'url': self.get_url(),
            'thread_alive': self.thread.is_alive() if self.thread else False
        }