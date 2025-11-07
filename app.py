import os
import logging
from datetime import datetime
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize the Slack app
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

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
    'deflation'
]

def format_timestamp(ts):
    """Convert Slack timestamp to readable time"""
    timestamp = datetime.fromtimestamp(float(ts))
    return timestamp.strftime('%I:%M %p')

def find_matching_keywords(text):
    """Find which keywords are present in the text"""
    text_lower = text.lower()
    return [keyword for keyword in KEYWORDS if keyword.lower() in text_lower]

def get_message_link(channel_id, message_ts, team_id):
    """Generate a permalink to a Slack message"""
    # Remove the dot from timestamp to create the message ID
    message_id = message_ts.replace('.', '')
    return f"https://slack.com/archives/{channel_id}/p{message_id}"

@app.shortcut("extract_thread_issues")
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
        
        # Send immediate acknowledgment
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="🔍 Analyzing thread for issues... This may take a moment."
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
                message_link = get_message_link(channel_id, msg.get("ts"), team_id)
                relevant_messages.append({
                    "text": text,
                    "user": msg.get("user", "Unknown"),
                    "ts": msg.get("ts"),
                    "keywords": matched_keywords,
                    "link": message_link
                })
        
        # Build output message
        if not relevant_messages:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="✅ No issues found! No messages contained the tracked keywords."
            )
            return
        
        # Format the output
        output_lines = [
            f"🎮 *Thread Analysis Results*",
            f"Found *{len(relevant_messages)}* message(s) with issue keywords:\n",
            "━" * 50 + "\n"
        ]
        
        for index, msg in enumerate(relevant_messages, 1):
            timestamp = format_timestamp(msg["ts"])
            keywords_str = ", ".join([f'"{k}"' for k in msg["keywords"]])
            
            output_lines.extend([
                f"*MESSAGE #{index}* -  ({timestamp})",
                f"Keywords: {keywords_str}",
                f"🔗 \n",
                f'"{msg["text"]}"\n',
                "━" * 50 + "\n"
            ])
        
        output_text = "\n".join(output_lines)
        
        # Post the summary to the thread
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=output_text
        )
        
        logger.info(f"Successfully analyzed thread with {len(relevant_messages)} relevant messages")
        
    except Exception as e:
        logger.error(f"Error processing shortcut: {e}")
        client.chat_postEphemeral(
            channel=shortcut["channel"]["id"],
            user=shortcut["user"]["id"],
            text=f"❌ Error analyzing thread: {str(e)}"
        )

# Health check endpoint for hosting platforms
@app.event("app_mention")
def handle_app_mention(event, say):
    say("👋 I'm running! Use the 'Extract Issues from Thread' shortcut on any message.")

if __name__ == "__main__":
    # For local development
    port = int(os.environ.get("PORT", 3000))
    app.start(port=port)