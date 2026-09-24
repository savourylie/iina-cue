import os

# A machine that also has Cue installed must keep this suite on checkout paths.
# setdefault would leave an inherited CUE_INSTALLED=1 in place.
os.environ["CUE_INSTALLED"] = "0"
