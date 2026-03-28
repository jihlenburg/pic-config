#!/usr/bin/env python3
"""Launch the config-pic web server."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("web.app:app", host="127.0.0.1", port=8642, reload=True)
