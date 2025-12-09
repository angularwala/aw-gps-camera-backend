"""
Data sanitization utilities for logging sensitive information
"""
import re
import json
from typing import Optional, Dict, Any

class DataSanitizer:
    """Sanitize sensitive data before logging"""
    
    # Sensitive field names to redact
    SENSITIVE_FIELDS = {
        'password', 'token', 'secret', 'api_key', 'access_token',
        'refresh_token', 'authorization', 'auth', 'jwt', 'bearer',
        'credit_card', 'cvv', 'ssn', 'social_security'
    }
    
    # Patterns to detect and redact sensitive data
    SENSITIVE_PATTERNS = [
        (r'Bearer\s+[\w\-\.]+', 'Bearer [REDACTED]'),
        (r'"password"\s*:\s*"[^"]*"', '"password":"[REDACTED]"'),
        (r'"token"\s*:\s*"[^"]*"', '"token":"[REDACTED]"'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]'),
    ]
    
    MAX_BODY_SIZE = 10000  # Max characters for request/response body logging
    
    @staticmethod
    def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary data"""
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            # Check if field name is sensitive
            if any(sensitive in key.lower() for sensitive in DataSanitizer.SENSITIVE_FIELDS):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = DataSanitizer.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    DataSanitizer.sanitize_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    @staticmethod
    def sanitize_string(text: Optional[str]) -> Optional[str]:
        """Sanitize sensitive patterns from string data"""
        if not text:
            return text
        
        # Limit size
        if len(text) > DataSanitizer.MAX_BODY_SIZE:
            text = text[:DataSanitizer.MAX_BODY_SIZE] + "...[TRUNCATED]"
        
        # Apply pattern replacements
        sanitized = text
        for pattern, replacement in DataSanitizer.SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    @staticmethod
    def sanitize_json_string(json_str: Optional[str]) -> Optional[str]:
        """Sanitize JSON string data"""
        if not json_str:
            return json_str
        
        try:
            # Parse JSON
            data = json.loads(json_str)
            # Sanitize dict
            sanitized = DataSanitizer.sanitize_dict(data)
            # Convert back to JSON string
            result = json.dumps(sanitized)
            
            # Limit size
            if len(result) > DataSanitizer.MAX_BODY_SIZE:
                result = result[:DataSanitizer.MAX_BODY_SIZE] + "...[TRUNCATED]"
            
            return result
        except json.JSONDecodeError:
            # If not valid JSON, sanitize as string
            return DataSanitizer.sanitize_string(json_str)
