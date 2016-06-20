#!/usr/bin/env python
"""
The patchew event framework
"""

_handlers = {}

_events = {}

def register_handler(event, handler):
    """Register an event hander. It will be called when the event is emitted."""
    _handlers.setdefault(event, [])
    _handlers[event].append(handler)

def declare_event(event, **params):
    """Declare an event that the caller will emit later, with kwarg names as
    the event argument names, and values as the descriptions."""
    assert event not in _events
    _events[event] = params

def emit_event(event, **params):
    """Emit an event that was previously declared, and call all the registered
    handlers."""
    assert event in _events
    for keyword in params:
        assert keyword in _events[event]
    for handler in _handlers.get(event, []):
        try:
            handler(event, **params)
        except Exception as e:
            import traceback
            traceback.print_exc(e)

