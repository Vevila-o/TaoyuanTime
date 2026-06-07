def normalize(event_list):
    """
    Normalizes the events in the event_list.
    Handles date formats and missing values.
    """
    normalized = []
    for evt in event_list:
        if not evt: continue
        
        # Normalize date
        ds = evt.get("date_start")
        if ds:
            # simple cleanup for feasibility test
            evt["date_start"] = ds.replace("/", "-").replace(".", "-")
            
        if not evt.get("fee"):
            evt["fee"] = "免費" # Assuming free if not specified
            
        normalized.append(evt)
    return normalized
