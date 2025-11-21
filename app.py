import os
import logging
import time
from datetime import datetime
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize the Slack app
slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Initialize Flask app for web server
flask_app = Flask(__name__)
handler = SlackRequestHandler(slack_app)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Keywords to search for
KEYWORDS = [
    'bug',
    'issue',
    'problem',
    'error',
    'broken',
    'not working',
    'failed',
    'crash',
    'incident',
    'urgent',
    'rattle',
    'deflation',
    'detachment',
    'faulty',
    'incorrect',
    'wrong'
]

def format_timestamp(ts):
    """Convert Slack timestamp to readable time"""
    timestamp = datetime.fromtimestamp(float(ts))
    return timestamp.strftime('%I:%M %p')

def find_matching_keywords(text):
    """Find which keywords are present in the text"""
    text_lower = text.lower()
    return [keyword for keyword in KEYWORDS if keyword.lower() in text_lower]

def get_message_link(client, channel_id, message_ts):
    """Generate a permalink to a Slack message using Slack API"""
    try:
        result = client.chat_getPermalink(
            channel=channel_id,
            message_ts=message_ts
        )
        return result["permalink"]
    except Exception as e:
        # Fallback to manual construction
        message_id = message_ts.replace('.', '')
        return f"https://sportabletech.slack.com/archives/{channel_id}/p{message_id}"

@slack_app.shortcut("extract_thread_issues")
def handle_extract_issues(ack, shortcut, client, logger):
    """Handle the message shortcut to extract issues from thread"""
    # Acknowledge the shortcut request
    ack()
    
    try:
        # Get thread and channel info
        thread_ts = shortcut["message"].get("thread_ts") or shortcut["message"]["ts"]
        channel_id = shortcut["channel"]["id"]
        user_id = shortcut["user"]["id"]
        team_id = shortcut["team"]["id"]
        
        # Post a loading message
        loading_msg = client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="🔍 Analyzing thread..."
        )
        
        # Fetch all replies in the thread
        result = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            limit=1000
        )
        
        messages = result.get("messages", [])
        
        # Filter messages that contain keywords
        relevant_messages = []
        for msg in messages:
            text = msg.get("text", "")
            matched_keywords = find_matching_keywords(text)
            if matched_keywords:
                message_link = get_message_link(client, channel_id, msg.get("ts"))
                relevant_messages.append({
                    "text": text,
                    "user": msg.get("user", "Unknown"),
                    "ts": msg.get("ts"),
                    "keywords": matched_keywords,
                    "link": message_link
                })
        
        #Build output message
        if not relevant_messages:
            # Update loading message to show no issues found
            client.chat_update(
                channel=channel_id,
                ts=loading_msg["ts"],
                text="✅ Analysis complete - No issues found!"
            )
            # Delete after 15 seconds
            time.sleep(15)
            client.chat_delete(
                channel=channel_id,
                ts=loading_msg["ts"]
            )
            return
        
        # Post header message
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"Found *{len(relevant_messages)}* message(s) with issue keywords:\n\n:warning: Summary may not contain all incidents, messages below may not relate to an issue or may be part of the same incident, please review before creating Support Tickets"
        )
        
        # Post each incident as a separate message
        for index, msg in enumerate(relevant_messages, 1):
            timestamp = format_timestamp(msg["ts"])
            keywords_str = ", ".join([f'"{k}"' for k in msg["keywords"]])
            
            individual_message = (
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"*MESSAGE #{index}* - ({timestamp})\n\n"
                f'"{msg["text"]}\n\n"'
                f"Keywords: {keywords_str}\n\n"
                f"<{msg['link']}|View message>\n\n"

            )
            
            # Post individual message
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=individual_message
            )
            
            # Small delay to avoid rate limits
            time.sleep(0.5)
        
        # Update loading message to completion message
        client.chat_update(
            channel=channel_id,
            ts=loading_msg["ts"],
            text="✅ Analysis complete!"
        )
        
        # Delete the completion message after 15 seconds
        time.sleep(15)
        client.chat_delete(
            channel=channel_id,
            ts=loading_msg["ts"]
        )
        
        logger.info(f"Successfully analyzed thread with {len(relevant_messages)} relevant messages")
        
    except Exception as e:
        logger.error(f"Error processing shortcut: {e}")
        client.chat_postEphemeral(
            channel=shortcut["channel"]["id"],
            user=shortcut["user"]["id"],
            text=f"❌ Error analyzing thread: {str(e)}"
        )

# Flask routes
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    """Handle Slack events"""
    return handler.handle(request)

@flask_app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return "Slack Thread Analyzer is running! 🚀", 200

# For local development
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)

# Expose the Flask app for gunicorn
app = flask_app