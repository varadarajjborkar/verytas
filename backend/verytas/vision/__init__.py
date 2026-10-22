"""Characters in images and video frames: found, cut out, identified and compared with the artwork.

Pixel matching (media/asset_match.py) recognises copies of the official artwork. It can't recognise a
mascot an AI has redrawn, which is exactly the case brands worry about: new pose, new style, and a
wrong colour or an extra limb. This package handles that case with three open models on the CPU:

- Grounding DINO (tiny) finds characters from a text prompt;
- SAM 2.1 (tiny) cuts each one out;
- DINOv2 (small) describes the cut-out, and its similarity to each official artwork says who it is.

media/fidelity.py then compares the cut-out with its artwork: colours missing or new, parts added or
lost.

The models need torch, which the API servers don't have, so they run in a separate worker
(`verytas.vision.worker`, its own environment from requirements-vision.lock). The API talks to it
through `verytas.vision.client`, which imports nothing heavy. The worker only measures; what counts as
a finding is decided in the review (prism/characters.py).
"""
