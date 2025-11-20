from telegram import Update
from telegram.ext import Application, MessageHandler, CallbackContext, filters
from PIL import Image
import asyncio
import os
import uuid
from datetime import datetime
from telegram import InputMediaPhoto
import io
import json

BOT_TOKEN = "7340883003:AAE2JliEsu9aLYeGtrNQc42z_P_zxe8ObWo"

CHANNEL_ID = "@kiyaShiffon"

LOGO_PATH = "logo.png"


ALLOWED_USERS  = [5301464167,1087968824,1267822460]

# Create directories for temporary files
os.makedirs("temp", exist_ok=True)
os.makedirs("processed", exist_ok=True)

def add_logo(photo_path, output_path):
    """Add logo to a single image in the bottom-right corner"""
    try:
        base_image = Image.open(photo_path)
        # logo = Image.open(LOGO_PATH)

        # # Resize logo
        # logo_width = int(base_image.width * 0.5)
        # logo_height = int(logo.height * (logo_width / logo.width))
        # logo = logo.resize((logo_width, logo_height), Image.LANCZOS)
        #  # Resize logo
        logo_width = int(base_image.width * 0.5)
        logo_height = int(logo.height * (logo_width / logo.width))
        logo = logo.resize((logo_width, logo_height), Image.LANCZOS)

        # Convert to RGBA for transparency
        if base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')
        if logo.mode != 'RGBA':
            logo = logo.convert('RGBA')

        # Calculate position for bottom-right corner with padding
        padding = 23  # Padding from bottom and right edges
        position = (
             padding,  # x-coordinate: right edge minus logo width minus padding
            padding  # y-coordinate: bottom edge minus logo height minus padding
        )

        # Paste logo at calculated position
        base_image.paste(logo, position, logo)
        
        # Save new image
        base_image.save(output_path)
        return output_path
    
    except Exception as e:
        print(f"Error adding logo to {photo_path}: {e}")
        raise

async def process_single_photo(photo_file, temp_dir):

    
    """Process a single photo and return the processed path"""
    try:
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        photo_path = os.path.join(temp_dir, f"temp_photo_{unique_id}.jpg")
        output_path = os.path.join(temp_dir, f"processed_photo_{unique_id}.png")
        
        # Download the photo
        await photo_file.download_to_drive(photo_path)
        
        # Add logo
        add_logo(photo_path, output_path)
        
        # Clean up temporary file
        os.remove(photo_path)
        
        return output_path
    except Exception as e:
        print(f"Error processing single photo: {e}")
        raise

async def handle_single_photo(update: Update, context: CallbackContext):
    print(update.message.chat.id,'chat id ')
    user_id = update.message.from_user.id
    print(user_id,'user id')
    if update.message.chat.type != "private":
        return 
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ You are not allowed to use this bot.")
        return

    """Handle single photo message"""
    try:
        processing_msg = await update.message.reply_text("🔄 Processing your image...")
        
        # Get the photo file
        photo_file = await update.message.photo[-1].get_file()
        
        # Process the photo
        processed_path = await process_single_photo(photo_file, "temp")
        
        # Send to channel
        with open(processed_path, 'rb') as photo:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID, 
                photo=photo,
                caption=""
            )
        
        # Clean up processed file
        os.remove(processed_path)
        
        await processing_msg.edit_text("✅ Image processed and sent successfully!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error processing image: {str(e)}")
        print(f"Error processing photo: {e}")


# Buffer to hold incoming album messages
album_buffer = {}
# Lock to prevent race conditions for the same media_group_id
album_locks = {}

async def handle_album_photos(update: Update, context: CallbackContext):
    print(update.message.chat.id,'chat id ')
    user_id = update.message.from_user.id
    print(user_id,'user id')
    if update.message.chat.type != "private":
        return 
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("❌ You are not allowed to use this bot.")
        return

    """Handle photos in a media group (album) and send them as an album"""
    try:
        # If no media_group_id, handle as single photo
        if not update.message.media_group_id:
            return await handle_single_photo(update, context)

        media_group_id = update.message.media_group_id

        # Initialize buffer and lock for this media_group_id if not exists
        if media_group_id not in album_buffer:
            album_buffer[media_group_id] = []
            album_locks[media_group_id] = asyncio.Lock()

        # Add the message to the buffer
        async with album_locks[media_group_id]:
            album_buffer[media_group_id].append(update.message)

            # If this is not the first message, skip to avoid starting a new task
            if len(album_buffer[media_group_id]) > 1:
                return

        # Start processing the album in a separate task
        async def process_album():
            try:
                # Wait briefly to collect any immediate subsequent messages
                await asyncio.sleep(1)  # Short buffer to catch rapid messages

                async with album_locks[media_group_id]:
                    # Get all messages for this album
                    album_msgs = album_buffer.pop(media_group_id, [])
                    if not album_msgs:
                        return

                    # Send processing message to the user who sent the first message
                    processing_msg = await album_msgs[0].reply_text(
                        f"🔄 Processing album of {len(album_msgs)} images..."
                    )

                    processed_files = []
                    for msg in album_msgs:
                        try:
                            # Get the highest resolution photo
                            photo_file = await msg.photo[-1].get_file()
                            processed_path = await process_single_photo(photo_file, "temp")

                            # Read file into memory for InputMediaPhoto
                            with open(processed_path, "rb") as f:
                                img_bytes = io.BytesIO(f.read())
                                img_bytes.name = f"watermarked_{str(uuid.uuid4())[:8]}.png"
                                processed_files.append(InputMediaPhoto(media=img_bytes))

                            # Clean up processed file
                            os.remove(processed_path)
                        except Exception as e:
                            print(f"❌ Error processing photo in album: {e}")
                            continue

                    # Send as album if there are processed files
                    if processed_files:
                        try:
                            await context.bot.send_media_group(
                                chat_id=CHANNEL_ID,
                                media=processed_files
                            )
                            await processing_msg.edit_text(
                                f"✅ Processed and sent {len(processed_files)} album images!"
                            )
                        except Exception as e:
                            await processing_msg.edit_text(f"❌ Error sending album: {str(e)}")
                            print(f"Error sending media group: {e}")
                    else:
                        await processing_msg.edit_text("❌ No images were processed successfully.")

                    # Clean up lock
                    if media_group_id in album_locks:
                        del album_locks[media_group_id]

            except Exception as e:
                print(f"Error in album processing task: {e}")
                try:
                    await album_msgs[0].reply_text(f"❌ Error processing album: {str(e)}")
                except:
                    pass

        # Run the album processing in a background task
        asyncio.create_task(process_album())

    except Exception as e:
        await update.message.reply_text(f"❌ Error initiating album processing: {str(e)}")
        print(f"Error in album handler: {e}")
        
async def handle_document_photos(update: Update, context: CallbackContext):
    print(update.message.chat.id,'chat id ')
    try:
        document = update.message.document
        if document.mime_type and document.mime_type.startswith('image/'):
            processing_msg = await update.message.reply_text("🔄 Processing document image...")
            
            # Get the document file
            doc_file = await document.get_file()
            unique_id = str(uuid.uuid4())[:8]
            photo_path = os.path.join("temp", f"doc_photo_{unique_id}.jpg")
            output_path = os.path.join("temp", f"doc_processed_{unique_id}.png")
            
            # Download the document
            await doc_file.download_to_drive(photo_path)
            
            # Add logo
            add_logo(photo_path, output_path)
            
            # Send to channel
            with open(output_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID, 
                    photo=photo,
                    caption=f"Document image processed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            
            # Clean up
            os.remove(photo_path)
            os.remove(output_path)
            
            await processing_msg.edit_text("✅ Document image processed and sent!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error processing document: {str(e)}")
        print(f"Error processing document: {e}")

def main():
    # Create Application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(60)
        .write_timeout(60)  
        .connect_timeout(60)
        .pool_timeout(60)
        .build()
    )
    
    # Add handlers for different types of image messages
    application.add_handler(MessageHandler(filters.PHOTO, handle_album_photos))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document_photos))
    
    # Optional: Add a command to check bot status
    from telegram.ext import CommandHandler
    
    async def start(update: Update, context: CallbackContext):
        await update.message.reply_text(
            "🤖 Bot is running!\n\n"
            "Send me photos (single or albums) and I'll add a logo and forward them to the channel."
        )
    
    application.add_handler(CommandHandler("start", start))

    # Start the bot
    print("Bot is running... Ready to handle multiple images!")
    application.run_polling(timeout=150)

if __name__ == "__main__":
    main()