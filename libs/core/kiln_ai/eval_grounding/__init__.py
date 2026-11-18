"""The grounding agent: makes one planned multi-turn eval case true for an OpenEnv server.

It picks reset arguments, finds what the case needs in a fresh environment, rehearses the
change, fills real specifics into the drafted simulated user, and writes a reference built
from what the server returned. Or it drops the case.
"""
