"""
Custom middleware for Cloudflare integration
"""
import logging

logger = logging.getLogger(__name__)


class CloudflareMiddleware:
    """
    Middleware to handle Cloudflare headers and real IP detection
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            # Get real IP from Cloudflare
            cf_connecting_ip = request.META.get('HTTP_CF_CONNECTING_IP')
            if cf_connecting_ip:
                request.META['REMOTE_ADDR'] = cf_connecting_ip
                logger.debug(f"Set real IP from Cloudflare: {cf_connecting_ip}")
            
            # Handle Cloudflare visitor scheme
            cf_visitor = request.META.get('HTTP_CF_VISITOR')
            if cf_visitor and '"scheme":"https"' in cf_visitor:
                # Set HTTPS headers for Django
                request.META['HTTPS'] = 'on'
                request.META['SERVER_PORT'] = '443'
                logger.debug("Set HTTPS from Cloudflare CF-Visitor header")
            
            # Handle forwarded protocol
            forwarded_proto = request.META.get('HTTP_X_FORWARDED_PROTO')
            if forwarded_proto == 'https':
                request.META['HTTPS'] = 'on'
                request.META['SERVER_PORT'] = '443'
                logger.debug("Set HTTPS from X-Forwarded-Proto header")
            
            # Fix Origin header for CSRF if missing or incorrect
            origin = request.META.get('HTTP_ORIGIN')
            referer = request.META.get('HTTP_REFERER', '')
            
            # If Origin is missing but Referer exists, extract origin from Referer
            if not origin and referer:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(referer)
                    origin = f"{parsed.scheme}://{parsed.netloc}"
                    request.META['HTTP_ORIGIN'] = origin
                    logger.debug(f"Set Origin from Referer: {origin}")
                except Exception as e:
                    logger.debug(f"Could not parse Referer: {e}")
            
            # If still no Origin, construct from Host header
            if not origin and request.META.get('HTTP_HOST'):
                # Determine scheme with priority: HTTPS header > X-Forwarded-Proto > CF-Visitor
                if request.META.get('HTTPS') == 'on':
                    scheme = 'https'
                elif request.META.get('HTTP_X_FORWARDED_PROTO') == 'https':
                    scheme = 'https'
                elif request.META.get('HTTP_CF_VISITOR') and '"scheme":"https"' in request.META.get('HTTP_CF_VISITOR', ''):
                    scheme = 'https'
                else:
                    scheme = 'http'
                
                host = request.META.get('HTTP_HOST')
                if host:
                    origin = f"{scheme}://{host}"
                    request.META['HTTP_ORIGIN'] = origin
                    logger.debug(f"Set Origin from Host: {origin}")

            response = self.get_response(request)
            return response
            
        except Exception as e:
            logger.error(f"Error in CloudflareMiddleware: {e}")
            # If there's an error, just continue without Cloudflare processing
            return self.get_response(request)

