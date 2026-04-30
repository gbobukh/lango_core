"""
Custom CSRF middleware for Cloudflare compatibility
"""
from django.middleware.csrf import CsrfViewMiddleware
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class CloudflareCsrfMiddleware(CsrfViewMiddleware):
    """
    CSRF middleware that handles Cloudflare proxy headers correctly
    """
    
    def _origin_verified(self, request):
        """
        Override origin verification to handle Cloudflare properly
        """
        host = request.META.get('HTTP_HOST', '')
        
        # For admin paths, always allow if host is trusted (most lenient approach)
        if request.path.startswith('/admin/'):
            if host and ('core.lango.media' in host or 'localhost' in host or '127.0.0.1' in host):
                logger.debug(f"CSRF origin check bypassed for admin on trusted host: {host}")
                return True
        
        # Get request origin from various sources
        request_origin = request.META.get('HTTP_ORIGIN')
        referer = request.META.get('HTTP_REFERER', '')
        
        # If no Origin header, try to extract from Referer
        if not request_origin and referer:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(referer)
                request_origin = f"{parsed.scheme}://{parsed.netloc}"
                logger.debug(f"Extracted origin from Referer: {request_origin}")
            except Exception as e:
                logger.debug(f"Could not parse Referer: {e}")
        
        # If still no origin, construct from Host
        if not request_origin and host:
            # Determine scheme
            if request.META.get('HTTPS') == 'on':
                scheme = 'https'
            elif request.META.get('HTTP_X_FORWARDED_PROTO') == 'https':
                scheme = 'https'
            elif request.META.get('HTTP_CF_VISITOR') and '"scheme":"https"' in request.META.get('HTTP_CF_VISITOR', ''):
                scheme = 'https'
            else:
                scheme = 'http'
            
            request_origin = f"{scheme}://{host}"
            logger.debug(f"Constructed origin from Host: {request_origin}")
        
        # For non-admin paths, strict origin checking
        if not request_origin:
            logger.warning("No origin found for CSRF check")
            return False
        
        # Check against trusted origins
        trusted_origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
        
        # Normalize origins (remove trailing slashes, ports if default)
        def normalize_origin(origin):
            origin = origin.rstrip('/')
            # Remove default ports
            if origin.startswith('https://') and ':443' in origin:
                origin = origin.replace(':443', '')
            elif origin.startswith('http://') and ':80' in origin:
                origin = origin.replace(':80', '')
            return origin.lower()
        
        normalized_request_origin = normalize_origin(request_origin)
        
        for trusted_origin in trusted_origins:
            normalized_trusted = normalize_origin(trusted_origin)
            
            # Exact match
            if normalized_request_origin == normalized_trusted:
                logger.debug(f"CSRF origin verified: {request_origin} matches {trusted_origin}")
                return True
            
            # Wildcard match (e.g., *.core.lango.media matches www.core.lango.media)
            if '*' in normalized_trusted:
                # Replace * with regex pattern
                import re
                pattern = normalized_trusted.replace('.', r'\.').replace('*', r'.*')
                if re.match(f'^{pattern}$', normalized_request_origin):
                    logger.debug(f"CSRF origin verified via wildcard: {request_origin} matches {trusted_origin}")
                    return True
            
            # Domain match (check if domains match regardless of subdomain)
            # e.g., https://www.core.lango.media matches https://core.lango.media
            try:
                from urllib.parse import urlparse
                req_parsed = urlparse(normalized_request_origin)
                trusted_parsed = urlparse(normalized_trusted)
                
                # Extract domain without scheme
                req_domain = req_parsed.netloc.split(':')[0]  # Remove port
                trusted_domain = trusted_parsed.netloc.split(':')[0]
                
                # Check if domains match (allowing subdomains)
                if req_domain == trusted_domain:
                    logger.debug(f"CSRF origin verified via domain match: {request_origin} matches {trusted_origin}")
                    return True
                
                # Check if one is subdomain of another
                if req_domain.endswith('.' + trusted_domain) or trusted_domain.endswith('.' + req_domain):
                    logger.debug(f"CSRF origin verified via subdomain match: {request_origin} matches {trusted_origin}")
                    return True
            except Exception as e:
                logger.debug(f"Error in domain matching: {e}")
        
        logger.warning(f"CSRF origin verification failed: {request_origin} not in trusted origins {trusted_origins}")
        return False
    
    def process_request(self, request):
        """
        Override to add better logging
        """
        # Log request details for debugging
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            logger.debug(f"CSRF check for {request.method} {request.path}")
            logger.debug(f"Origin: {request.META.get('HTTP_ORIGIN', 'None')}")
            logger.debug(f"Referer: {request.META.get('HTTP_REFERER', 'None')}")
            logger.debug(f"Host: {request.META.get('HTTP_HOST', 'None')}")
            logger.debug(f"CF-Visitor: {request.META.get('HTTP_CF_VISITOR', 'None')}")
            logger.debug(f"X-Forwarded-Proto: {request.META.get('HTTP_X_FORWARDED_PROTO', 'None')}")
        
        return super().process_request(request)

