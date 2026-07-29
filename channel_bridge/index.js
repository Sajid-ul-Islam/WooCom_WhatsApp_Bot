const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const cors = require('cors');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.CHANNEL_BRIDGE_PORT || 3001;

let isReady = false;
let isAuthenticated = false;
let lastQr = null;

// Initialize WhatsApp Web Client with LocalAuth for session persistence
const client = new Client({
    authStrategy: new LocalAuth({ dataPath: './.wwebjs_auth' }),
    puppeteer: {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu'
        ]
    }
});

// Event: QR Code generated (requires phone scan)
client.on('qr', (qr) => {
    lastQr = qr;
    isReady = false;
    isAuthenticated = false;
    console.log('\n==================================================');
    console.log('📢 WHATSAPP CHANNEL BRIDGE — ACTION REQUIRED');
    console.log('Scan the QR code below using the WhatsApp phone number');
    console.log('that is an ADMIN of your WhatsApp Channel:');
    console.log('==================================================\n');
    qrcode.generate(qr, { small: true });
});

// Event: Authenticated successfully
client.on('authenticated', () => {
    isAuthenticated = true;
    lastQr = null;
    console.log('✅ WhatsApp Channel Bridge authenticated successfully.');
});

// Event: Client Ready
client.on('ready', () => {
    isReady = true;
    console.log('🚀 WhatsApp Channel Bridge is READY and connected!');
});

// Event: Authentication Failure
client.on('auth_failure', (msg) => {
    isReady = false;
    isAuthenticated = false;
    console.error('❌ WhatsApp Channel Bridge Auth Failure:', msg);
});

// Event: Disconnected
client.on('disconnected', (reason) => {
    isReady = false;
    isAuthenticated = false;
    console.warn('⚠️ WhatsApp Channel Bridge Disconnected:', reason);
    console.log('Attempting re-initialization...');
    client.initialize().catch(err => console.error('Re-init failed:', err));
});

// -----------------------------------------------------------------------------
// REST API ROUTES
// -----------------------------------------------------------------------------

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({
        status: isReady ? 'ready' : (isAuthenticated ? 'authenticated' : 'needs_qr'),
        ready: isReady,
        authenticated: isAuthenticated,
        hasQr: !!lastQr
    });
});

// List managed channels / newsletters
app.get('/channels', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ error: 'WhatsApp client is not ready yet. Please scan QR code.' });
    }

    try {
        const chats = await client.getChats();
        // Filter channels/newsletters
        const channels = chats
            .filter(c => c.isNewsletter || (c.id && c.id._serialized && c.id._serialized.includes('@newsletter')))
            .map(c => ({
                id: c.id._serialized,
                name: c.name,
                unreadCount: c.unreadCount
            }));

        res.json({ status: 'ok', channels });
    } catch (err) {
        console.error('Error fetching channels:', err);
        res.status(500).json({ error: err.message });
    }
});

// Post a message/announcement to a WhatsApp Channel
app.post('/post-channel', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({
            error: 'WhatsApp client is not ready. Please complete QR code login first.'
        });
    }

    const { target, message, imageUrl } = req.body;
    const channelTarget = target || process.env.WHATSAPP_CHANNEL_JID;

    if (!channelTarget) {
        return res.status(400).json({
            error: 'Target channel JID (e.g. 120363xxx@newsletter) is required.'
        });
    }

    if (!message && !imageUrl) {
        return res.status(400).json({ error: 'Either message or imageUrl is required.' });
    }

    try {
        let chatTarget = channelTarget.trim();

        // If user passed a web link like https://whatsapp.com/channel/0029Vb8OUEX2v1IuuJP6Z11K, attempt lookup
        if (chatTarget.includes('whatsapp.com/channel/')) {
            const chats = await client.getChats();
            const matching = chats.find(c => c.isNewsletter || (c.id && c.id._serialized.includes('@newsletter')));
            if (matching) {
                chatTarget = matching.id._serialized;
            }
        }

        // Ensure @newsletter suffix if missing and numeric
        if (!chatTarget.includes('@') && /^\d+$/.test(chatTarget)) {
            chatTarget = `${chatTarget}@newsletter`;
        }

        let sentMsg;
        if (imageUrl) {
            const media = await MessageMedia.fromUrl(imageUrl, { unsafeMime: true });
            sentMsg = await client.sendMessage(chatTarget, media, { caption: message || '' });
        } else {
            sentMsg = await client.sendMessage(chatTarget, message);
        }

        console.log(`📢 Channel Post sent successfully to ${chatTarget}`);
        res.json({
            status: 'ok',
            message: 'Post published to WhatsApp Channel successfully',
            target: chatTarget,
            messageId: sentMsg.id ? sentMsg.id._serialized : null
        });
    } catch (err) {
        console.error('Failed to post to WhatsApp Channel:', err);
        res.status(500).json({ error: err.message || 'Failed to post to WhatsApp Channel' });
    }
});

// Start client initialization
client.initialize().catch(err => {
    console.error('Failed to initialize WhatsApp Web Client:', err);
});

// Start Express server
app.listen(PORT, () => {
    console.log(`🚀 WhatsApp Channel Bridge HTTP API running on http://localhost:${PORT}`);
});
