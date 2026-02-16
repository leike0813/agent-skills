#!/usr/bin/env python3
import json
import yaml
import sys
import os
import re
import argparse

def parse_markdown_table(content):
    """
    Parse markdown table.
    Expects header row with specific keywords.
    """
    lines = content.strip().split('\n')
    recipients = []
    headers = []
    
    # Simple table parser
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith('|'): continue
        
        cells = [c.strip() for c in line.split('|') if c]
        
        # Detect header
        if not headers:
            if '称谓' in cells or 'title' in cells or 'Title' in cells:
                headers = cells
                # Normalize headers
                headers = ['title' if '称谓' in h or 'title' in h.lower() else h for h in headers]
                headers = ['relation' if '关系' in h or 'relation' in h.lower() else h for h in headers]
                headers = ['name' if '姓名' in h or 'name' in h.lower() else h for h in headers]
                headers = ['age' if '年龄' in h or 'age' in h.lower() else h for h in headers]
                headers = ['gender' if '性别' in h or 'gender' in h.lower() else h for h in headers]
                headers = ['notes' if '注意' in h or 'notes' in h.lower() else h for h in headers]
                continue
        
        # Skip separator line
        if '---' in line:
            continue
            
        # Data row
        if headers:
            recipient = {}
            for j, cell in enumerate(cells):
                if j < len(headers):
                    key = headers[j]
                    if key in ['title', 'relation', 'name', 'age', 'gender', 'notes']:
                        recipient[key] = cell
            
            if 'title' in recipient or 'relation' in recipient:
                 recipients.append(recipient)

    return recipients

def parse_file(filepath):
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if ext in ['.json']:
            return json.loads(content)
        elif ext in ['.yaml', '.yml']:
            return yaml.safe_load(content)
        elif ext in ['.md', '.markdown', '.txt']:
            # Try parsing as markdown table first
            recipients = parse_markdown_table(content)
            if not recipients:
                 # TODO: Add logic for list parsing if table fails
                 pass
            return recipients
        else:
            print(f"Unsupported file extension: {ext}", file=sys.stderr)
            return []
    except Exception as e:
        print(f"Error parsing file: {e}", file=sys.stderr)
        return []

def normalize_recipient(recipient):
    """
    Normalize keys from Chinese to English
    """
    normalized = {}
    key_map = {
        '称谓': 'title', 'title': 'title', 'Title': 'title',
        '关系': 'relation', 'relation': 'relation', 'Relation': 'relation',
        '姓名': 'name', 'name': 'name', 'Name': 'name',
        '年龄': 'age', 'age': 'age', 'Age': 'age',
        '性别': 'gender', 'gender': 'gender', 'Gender': 'gender',
        '注意': 'notes', 'notes': 'notes', 'Notes': 'notes',
        '需要注意的点': 'notes', '注意事项': 'notes'
    }
    
    for k, v in recipient.items():
        # strict match first
        if k in key_map:
            normalized[key_map[k]] = v
        else:
            # partial match fallback
            found = False
            for map_k, map_v in key_map.items():
                 if map_k in k:
                     normalized[map_v] = v
                     found = True
                     break
            if not found:
                normalized[k] = v
                
    return normalized

def validate_recipients(recipients):
    valid = []
    invalid = []
    
    for r in recipients:
        if not isinstance(r, dict):
            invalid.append({"data": r, "error": "Item is not a dictionary"})
            continue
            
        # Normalize keys
        r = normalize_recipient(r)
            
        if 'title' not in r or not r['title']:
            # Try to infer title from name if title missing
            if 'name' in r and r['name']:
                 r['title'] = r['name'] # Fallback
            else:
                invalid.append({"data": r, "error": "Missing required field: title"})
                continue
        
        if 'relation' not in r or not r['relation']:
            r['relation'] = "朋友" # Default fallback
            
        valid.append(r)
        
    return valid, invalid

def main():
    parser = argparse.ArgumentParser(description='Parse recipient list file')
    parser.add_argument('file', help='Path to recipient file')
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        sys.exit(1)
        
    raw_recipients = parse_file(args.file)
    
    if raw_recipients is None:
        raw_recipients = []
        
    if not isinstance(raw_recipients, list):
         print(json.dumps({"error": "Root element must be a list"}))
         sys.exit(1)

    valid, invalid = validate_recipients(raw_recipients)
    
    print(json.dumps({
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "recipients": valid,
        "errors": invalid
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
