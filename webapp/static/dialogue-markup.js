/**
 * Dialogue Markup Parser for TTS
 * Supports formats:
 * - [Speaker]: text
 * - [Speaker:emotion]: text
 * - [VoiceID]: text
 * - [VoiceID:emotion]: text
 */

// Default speaker-to-voice mapping for all voices with emotion/style support
let speakerVoiceMap = {
    // Generic speaker names
    'SpeakerA': 'en-US-GuyNeural',
    'SpeakerB': 'en-US-JennyNeural',
    'SpeakerC': 'en-US-AriaNeural',
    'SpeakerD': 'en-US-DavisNeural',
    'Narrator': 'en-US-EmmaMultilingualNeural',

    // English (US) voices with emotions
    'Jenny': 'en-US-JennyNeural',
    'Guy': 'en-US-GuyNeural',
    'Aria': 'en-US-AriaNeural',
    'Davis': 'en-US-DavisNeural',
    'Jane': 'en-US-JaneNeural',
    'Jason': 'en-US-JasonNeural',
    'Sara': 'en-US-SaraNeural',
    'Tony': 'en-US-TonyNeural',
    'Nancy': 'en-US-NancyNeural',
    'Amber': 'en-US-AmberNeural',
    'Ana': 'en-US-AnaNeural',
    'Ashley': 'en-US-AshleyNeural',
    'Brandon': 'en-US-BrandonNeural',
    'Christopher': 'en-US-ChristopherNeural',
    'Cora': 'en-US-CoraNeural',
    'Elizabeth': 'en-US-ElizabethNeural',
    'Eric': 'en-US-EricNeural',
    'Jacob': 'en-US-JacobNeural',
    'Michelle': 'en-US-MichelleNeural',
    'Monica': 'en-US-MonicaNeural',
    'Roger': 'en-US-RogerNeural',
    'Steffan': 'en-US-SteffanNeural',

    // English (UK) voices with emotions
    'Sonia': 'en-GB-SoniaNeural',
    'Ryan': 'en-GB-RyanNeural',
    'Libby': 'en-GB-LibbyNeural',
    'Abbi': 'en-GB-AbbiNeural',
    'Alfie': 'en-GB-AlfieNeural',
    'Bella': 'en-GB-BellaNeural',
    'Elliot': 'en-GB-ElliotNeural',
    'Ethan': 'en-GB-EthanNeural',
    'Hollie': 'en-GB-HollieNeural',
    'Maisie': 'en-GB-MaisieNeural',
    'Noah': 'en-GB-NoahNeural',
    'Oliver': 'en-GB-OliverNeural',
    'Olivia': 'en-GB-OliviaNeural',
    'Thomas': 'en-GB-ThomasNeural',

    // English (Australia) voices with emotions
    'Natasha': 'en-AU-NatashaNeural',
    'William': 'en-AU-WilliamNeural',
    'Annette': 'en-AU-AnnetteNeural',
    'Carly': 'en-AU-CarlyNeural',
    'Darren': 'en-AU-DarrenNeural',
    'Duncan': 'en-AU-DuncanNeural',
    'Elsie': 'en-AU-ElsieNeural',
    'Freya': 'en-AU-FreyaNeural',
    'Joanne': 'en-AU-JoanneNeural',
    'Ken': 'en-AU-KenNeural',
    'Kim': 'en-AU-KimNeural',
    'Neil': 'en-AU-NeilNeural',
    'Tim': 'en-AU-TimNeural',
    'Tina': 'en-AU-TinaNeural',

    // Chinese (Mandarin) voices with emotions
    'Xiaoxiao': 'zh-CN-XiaoxiaoNeural',
    'Yunxi': 'zh-CN-YunxiNeural',
    'Yunjian': 'zh-CN-YunjianNeural',
    'Xiaoyi': 'zh-CN-XiaoyiNeural',
    'Yunyao': 'zh-CN-YunyaoNeural',
    'Yunfeng': 'zh-CN-YunfengNeural',
    'Xiaochen': 'zh-CN-XiaochenNeural',
    'Xiaohan': 'zh-CN-XiaohanNeural',
    'Xiaomeng': 'zh-CN-XiaomengNeural',
    'Xiaoqiu': 'zh-CN-XiaoqiuNeural',
    'Xiaoqiu2': 'zh-CN-XiaoqiuNeural',
    'Xiaorui': 'zh-CN-XiaoruiNeural',
    'Xiaoshuang': 'zh-CN-XiaoshuangNeural',
    'Xiaoxuan': 'zh-CN-XiaoxuanNeural',
    'Xiaoyan': 'zh-CN-XiaoyanNeural',
    'Xiaoyou': 'zh-CN-XiaoyouNeural',
    'Yunhao': 'zh-CN-YunhaoNeural',
    'Yunyang': 'zh-CN-YunyangNeural',
    'Yunye': 'zh-CN-YunyeNeural',
    'Yunze': 'zh-CN-YunzeNeural',

    // Common name aliases
    'John': 'en-US-GuyNeural',
    'Mary': 'en-US-JennyNeural',
    'Sarah': 'en-US-SaraNeural',
    'Mike': 'en-US-GuyNeural',
    'Emma': 'en-US-EmmaMultilingualNeural'
};

/**
 * Get voice ID for a speaker name (case-insensitive)
 */
function getSpeakerVoice(speakerName) {
    // Try exact match first
    if (speakerVoiceMap[speakerName]) {
        return speakerVoiceMap[speakerName];
    }

    // Try case-insensitive match
    const lowerName = speakerName.toLowerCase();
    for (const [key, value] of Object.entries(speakerVoiceMap)) {
        if (key.toLowerCase() === lowerName) {
            return value;
        }
    }

    return null;
}

/**
 * Parse dialogue markup from text
 */
function parseDialogueMarkup(text) {
    const lines = text.trim().split('\n');
    const chunks = [];
    const markupPattern = /^\[([^\]:]+)(?::([^\]]+))?\]:\s*(.+)$/;

    for (let line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        const match = trimmed.match(markupPattern);
        if (match) {
            const speakerOrVoice = match[1].trim();
            const emotion = match[2] ? match[2].trim() : null;
            const content = match[3].trim();

            // Check if it's a voice ID (contains hyphen) or speaker name
            const voice = speakerOrVoice.includes('-')
                ? speakerOrVoice  // Direct voice ID like "en-US-GuyNeural"
                : getSpeakerVoice(speakerOrVoice);  // Map speaker name like "John"

            chunks.push({
                content: content,
                voice: voice,
                emotion: emotion,
                intensity: 2,
                pitch: 0,
                speed: 0,
                volume: 0
            });
        } else {
            // No markup detected, treat as regular text
            chunks.push({
                content: trimmed,
                voice: null,
                emotion: null,
                intensity: 2,
                pitch: 0,
                speed: 0,
                volume: 0
            });
        }
    }

    return chunks;
}

/**
 * Check if text contains dialogue markup
 */
function hasDialogueMarkup(text) {
    return /^\[([^\]:]+)(?::([^\]]+))?\]:/m.test(text);
}

/**
 * Add a new speaker mapping
 */
function addSpeakerMapping(speakerName, voiceId) {
    speakerVoiceMap[speakerName] = voiceId;
}

/**
 * Remove a speaker mapping
 */
function removeSpeakerMapping(speakerName) {
    delete speakerVoiceMap[speakerName];
}

/**
 * Get all speaker mappings
 */
function getAllSpeakerMappings() {
    return { ...speakerVoiceMap };
}

/**
 * Update speaker mapping
 */
function updateSpeakerMapping(oldName, newName, voiceId) {
    if (oldName !== newName) {
        delete speakerVoiceMap[oldName];
    }
    speakerVoiceMap[newName] = voiceId;
}
