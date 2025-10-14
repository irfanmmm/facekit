import math

def is_user_in_radius(branch_lat, branch_lng, user_lat, user_lng, radius_in_meters):
    # Earth’s radius in meters
    R = 6371000  
    
    # Convert all lat/lon from degrees to radians
    lat1 = math.radians(branch_lat)
    lon1 = math.radians(branch_lng)
    lat2 = math.radians(user_lat)
    lon2 = math.radians(user_lng)

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    # Distance in meters
    distance = R * c

    # Check if user is inside the radius
    return distance <= radius_in_meters, round(distance, 2)
