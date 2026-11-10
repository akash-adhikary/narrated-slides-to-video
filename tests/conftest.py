import os

# Tests assume the plain neutral brand unless a test opts in to the bundled ThoughtSpot default.
os.environ.setdefault("HTML2MP4_BRAND", "neutral")
