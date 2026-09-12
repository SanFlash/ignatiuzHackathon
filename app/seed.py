"""Twenty-five authored questions: five competencies × five difficulty levels."""
from uuid import uuid5, NAMESPACE_URL

DEMO_ID = str(uuid5(NAMESPACE_URL, 'adaptive-assessment/python-backend-v1'))
SKILLS = ['Python Fundamentals', 'REST APIs', 'SQL', 'Debugging', 'System Design']
# difficulty, type, prompt, options or rubric concepts, correct answer
BANK = {
'Python Fundamentals': [
(1, 'MCQ', 'Which Python collection is mutable?', ['tuple', 'list', 'str', 'frozenset'], 'list'),
(2, 'MCQ', 'What does len({1, 1, 2}) return?', ['1', '2', '3', 'An exception'], '2'),
(3, 'Subjective', 'Why can a mutable default argument cause bugs? Show a safer function design.', ['default|defaults', 'shared|reuse|reused', 'None', 'new|fresh'], None),
(4, 'MCQ', 'A generator iterates over a large input. Which statement is accurate?', ['It always stores every result', 'It yields values lazily and preserves execution state', 'It runs in a separate thread', 'It cannot raise exceptions'], 'It yields values lazily and preserves execution state'),
(5, 'Subjective', 'Design concurrent processing for mixed CPU-bound and I/O-bound Python tasks. Explain limits and cancellation.', ['process|processes|multiprocessing', 'asyncio|threads|thread', 'GIL|global interpreter lock', 'cancel|cancellation', 'timeout|timeouts'], None)],
'REST APIs': [
(1, 'MCQ', 'Which method normally retrieves a resource without changing it?', ['GET', 'POST', 'PATCH', 'DELETE'], 'GET'),
(2, 'MCQ', 'Which status code indicates a newly created resource?', ['200', '201', '404', '500'], '201'),
(3, 'Subjective', 'Explain how idempotency prevents duplicate payment creation when clients retry.', ['idempotency|idempotent', 'key|token', 'retry|retries', 'store|persist|database'], None),
(4, 'MCQ', 'How can a client avoid overwriting a resource changed since it was fetched?', ['Always retry POST', 'Send If-Match with the resource ETag', 'Disable TLS', 'Use only GET'], 'Send If-Match with the resource ETag'),
(5, 'Subjective', 'Design robust retries and overload handling for an API with intermittent upstream failures.', ['backoff', 'jitter', 'timeout|timeouts', 'circuit breaker', 'idempotency|idempotent'], None)],
'SQL': [
(1, 'MCQ', 'Which clause filters rows before grouping?', ['ORDER BY', 'WHERE', 'HAVING', 'LIMIT'], 'WHERE'),
(2, 'MCQ', 'Which join preserves all rows from the left table?', ['INNER JOIN', 'LEFT JOIN', 'CROSS JOIN', 'Only RIGHT JOIN'], 'LEFT JOIN'),
(3, 'Subjective', 'A query filters orders by customer_id and orders by created_at. Explain an indexing and validation approach.', ['index|indexes', 'customer_id', 'created_at', 'EXPLAIN|query plan', 'write|writes|storage'], None),
(4, 'MCQ', 'What does ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC) assign?', ['One total count', 'A row sequence per customer, newest first', 'A random key', 'A rank shared by all ties'], 'A row sequence per customer, newest first'),
(5, 'Subjective', 'Two transactions update overlapping rows in different orders. Explain deadlock prevention and recovery.', ['lock|locks', 'order|ordering', 'transaction|transactions', 'retry|retries', 'rollback|roll back'], None)],
'Debugging': [
(1, 'MCQ', 'What should you inspect first when a Python exception occurs?', ['Change every dependency', 'The traceback and failing line', 'Delete the tests', 'Ignore the exception'], 'The traceback and failing line'),
(2, 'MCQ', 'Which test best protects a fixed bug from returning?', ['An unrelated passing test', 'A regression test that fails before the fix', 'A screenshot of the editor', 'No test is needed'], 'A regression test that fails before the fix'),
(3, 'Subjective', 'An endpoint intermittently returns 500 under concurrent load. Describe a systematic investigation.', ['reproduce|reproduction', 'log|logs|trace|traces', 'concurrency|concurrent|race', 'isolate', 'test|tests'], None),
(4, 'MCQ', 'A service shows increasing resident memory. What most directly tests for retained Python objects?', ['Compare tracemalloc snapshots under repeated load', 'Increase log verbosity forever', 'Disable all exceptions', 'Only inspect CPU frequency'], 'Compare tracemalloc snapshots under repeated load'),
(5, 'Subjective', 'Diagnose a production-only latency regression across services without logging sensitive payloads.', ['trace|tracing|correlation', 'percentile|p95|p99', 'profile|profiling', 'redact|redaction|sensitive', 'rollback|canary'], None)],
'System Design': [
(1, 'MCQ', 'What is a common purpose of a load balancer?', ['Distribute traffic across servers', 'Store all passwords', 'Replace database backups', 'Compile Python'], 'Distribute traffic across servers'),
(2, 'MCQ', 'Why are stateless API servers easier to scale horizontally?', ['They require no storage anywhere', 'Requests can be handled by any replica without local session dependence', 'They never fail', 'They eliminate network latency'], 'Requests can be handled by any replica without local session dependence'),
(3, 'Subjective', 'Design a horizontally scalable API. Explain state, traffic distribution, storage and caching.', ['stateless', 'load balancer|load balancing', 'database|storage', 'cache|caching', 'trade-off|tradeoff|trade-offs'], None),
(4, 'MCQ', 'An at-least-once message queue can redeliver messages. How should a consumer protect side effects?', ['Assume each message appears once', 'Use an idempotent handler with durable deduplication', 'Remove all acknowledgments', 'Keep deduplication only in a local variable'], 'Use an idempotent handler with durable deduplication'),
(5, 'Subjective', 'Design a multi-region order system. Discuss consistency during network partitions and disaster recovery.', ['consistency|consistent', 'partition|partitions', 'replication|replica', 'failover', 'RPO|recovery point', 'RTO|recovery time'], None)]}


def seed_demo(repo):
    if not repo.get_assessment(DEMO_ID):
        repo.create_assessment({'id': DEMO_ID, 'title': 'Python Backend Developer',
        'job_title': 'Backend Engineer', 'description': 'Explore Python, APIs, data, debugging and architecture through an adaptive technical assessment.',
        'max_questions': 15, 'confidence_target': .70, 'competencies': SKILLS, 'priorities': {s: 1 for s in SKILLS}})
    existing_ids = {q['id'] for q in repo.list_questions(DEMO_ID)}
    for skill, rows in BANK.items():
        for difficulty, kind, prompt, material, correct in rows:
            question_id = str(uuid5(NAMESPACE_URL, f'{DEMO_ID}/{skill}/{difficulty}'))
            if question_id in existing_ids:
                continue
            repo.create_question({'id': question_id,
                'assessment_id': DEMO_ID, 'question_text': prompt, 'skill': skill, 'difficulty': difficulty,
                'question_type': kind, 'options': material if kind == 'MCQ' else [], 'correct_answer': correct,
                'rubric': {'concepts': material, 'min_words': 40} if kind == 'Subjective' else {}, 'points': 1})
    return DEMO_ID
