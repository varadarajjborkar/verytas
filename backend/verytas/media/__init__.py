"""Turning images and documents into checkable text and pixels.

Everything here is local and deterministic: decoding with size limits, PDF and
Word extraction, OCR, pixel redaction and brand-asset matching. The cloud
vision model lives in providers/vision.py and is only reached through Prism's
agents, after redaction.
"""
