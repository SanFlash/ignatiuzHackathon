"""Safe error categories: never expose provider bodies, credentials or answers."""
import traceback
from uuid import uuid4


def describe_failure(exc, database=False):
    code = str(getattr(exc, 'code', ''))
    if code in {'PGRST205', 'PGRST204', 'PGRST202', '42P01', '42703', '42883'}:
        return 'DB_SCHEMA_MISSING', ('The database schema is missing or outdated. The administrator must run '
                                   'supabase/schema.sql and restart the app. For a local demo, set DATABASE_MODE=demo.')
    if code in {'PGRST301', 'PGRST302', '42501', '28000', '28P01'}:
        return 'DB_ACCESS_DENIED', 'Database access was denied. Check the server-side Supabase key and permissions.'
    if database:
        return 'DB_UNAVAILABLE', 'The database is unavailable. Check its connection and configuration; existing data has not been switched to demo mode.'
    return 'APP_ERROR', 'The request could not be completed. Share the error reference and the terminal log with the administrator.'


def log_failure(logger, exc, database=False):
    reference = uuid4().hex[:12]
    code, message = describe_failure(exc, database)
    # Frame metadata provides useful diagnostics without exception payloads or local variable values.
    logger.error('reference=%s category=%s exception=%s frames=%s', reference, code,
                 type(exc).__name__, traceback.extract_tb(exc.__traceback__))
    return reference, code, message
