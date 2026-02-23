import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def main():
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    params = {"address": "Amsterdam", "key": api_key}
    
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
        print("Geocoding Response:")
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(main())
