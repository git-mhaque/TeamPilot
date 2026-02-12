import argparse
from html import parser
import os
import sys
import re
from dotenv import load_dotenv
import markdown2
from atlassian import Confluence

# Load environment variables from .env file
load_dotenv()

def publish_report():
    print("Processing configurations and arguments...")
    parser = argparse.ArgumentParser(description="Publish Markdown to Confluence via PAT")
    
    # Required Arguments
    parser.add_argument("--file", required=True, help="Path to the .md file")
    parser.add_argument("--title", required=True, help="Title of the Confluence page")
        
    # Configuration
    parser.add_argument("--url", default=os.getenv("CONFLUENCE_URL"), help="Base URL")
    parser.add_argument("--token", default=os.getenv("CONFLUENCE_PAT"), help="Personal Access Token")
    parser.add_argument("--space", default=os.getenv("CONFLUENCE_SPACE_KEY"), help="Confluence Space key")
    parser.add_argument("--parent", default=os.getenv("CONFLUENCE_PARENT_PAGE_ID"), help="The ID of the parent page to nest this report under")
    parser.add_argument("--insecure", action="store_true", help="Skip SSL verification")


    args = parser.parse_args()

    if not args.url or not args.token:
        print("Error: Missing URL or PAT. Set CONFLUENCE_URL and CONFLUENCE_PAT env vars.")
        sys.exit(1)

    conf = Confluence(url=args.url, token=args.token, verify_ssl=not args.insecure)


    # 1. Read Markdown
    print(f"Reading Markdown file: {args.file}")
    with open(args.file, "r", encoding="utf-8") as f:
        md_content = f.read()

    # 2. Get or Create Page ID (Needed to attach files)
    if conf.page_exists(args.space, args.title):
        page_id = conf.get_page_id(args.space, args.title)
    else:
        res = conf.create_page(args.space, args.title, body="", parent_id=args.parent)
        page_id = res['id']
    print(f"Using page ID: {page_id} for updates and attachments.")


    # 3. Convert remaining MD to HTML
    html_body = markdown2.markdown(md_content, extras=["tables", "fenced-code-blocks"])
    print("Converted Markdown to HTML. Final content length:", len(html_body))

    # TODO: move below to config or env vars
    img_base_path = "./reports/"

    # 4. Handle Images: Find all ![alt](path)
    # finditer gives us access to the 'full match' and the 'groups'
    image_matches = list(re.finditer(r'!\[.*?\]\((.*?)\)', md_content))

    for match in image_matches:
        full_md_match = match.group(0)  # The entire string: ![alt](path)
        img_path = match.group(1)      # Just the path: path/to/image.png
        
        if os.path.exists(img_base_path + img_path):
            filename = os.path.basename(img_path)
            
            print(f"Uploading {filename}...")
            conf.attach_file(img_base_path + img_path, name=filename, page_id=page_id)
            
            # Create the Confluence-specific XML
            confluence_img_xml = f'<ac:image><ri:attachment ri:filename="{filename}" /></ac:image>'
            
            # Replace the specific full match in the content
            html_body = re.sub(rf'<img src="{re.escape(img_path)}".*?>', confluence_img_xml, html_body)
            #md_content = md_content.replace(full_md_match, confluence_img_xml)
        else:
            print(f"Warning: Image path not found: {img_path}")

    # 5. Update the page with the final content
    conf.update_page(
        page_id=page_id,
        title=args.title,
        body=html_body,
        representation='storage'
    )
    print(f"Published successfully to ID: {page_id}")

if __name__ == "__main__":
    publish_report()