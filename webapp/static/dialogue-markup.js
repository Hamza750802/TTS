/**
 * Dialogue Markup Parser for TTS
 * Supports formats:
 * - [Speaker]: text
 * - [Speaker:emotion]: text
 * - [VoiceID]: text
 * - [VoiceID:emotion]: text
 */

// Default speaker-to-voice mapping
let speakerVoiceMap = {
    'SpeakerA': 'en-US-GuyNeural',
    'SpeakerB': 'en-US-JennyNeural',
    'SpeakerC': 'en-US-AriaNeural',
    'SpeakerD': 'en-US-DavisNeural',
    'John': 'en-US-GuyNeural',
    'Mary': 'en-US-JennyNeural',
    'Sarah': 'en-US-JennyNeural',
    'Mike': 'en-US-GuyNeural',
    'Narrator': 'en-US-EmmaMultilingualNeural'
};

/**
 * Get voice ID for a speaker name
 */
function getSpeakerVoice(speakerName) {
    return speakerVoiceMap[speakerName] || null;
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
