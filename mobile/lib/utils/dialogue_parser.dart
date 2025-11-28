import '../models/dialogue_chunk.dart';

/// Dialogue markup parser for multi-speaker TTS
/// Supports formats:
/// - [Speaker]: text
/// - [Speaker:emotion]: text
/// - [VoiceID]: text (e.g., [en-US-GuyNeural]: Hello)

class DialogueParser {
  /// Default speaker-to-voice mapping
  static const Map<String, String> speakerVoiceMap = {
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

    // English (UK) voices
    'Sonia': 'en-GB-SoniaNeural',
    'Ryan': 'en-GB-RyanNeural',

    // Common name aliases
    'John': 'en-US-GuyNeural',
    'Mary': 'en-US-JennyNeural',
    'Sarah': 'en-US-SaraNeural',
    'Mike': 'en-US-GuyNeural',
    'Emma': 'en-US-EmmaMultilingualNeural',
  };

  /// Regular expression for parsing dialogue markup
  static final RegExp _markupPattern = RegExp(r'^\[([^\]:]+)(?::([^\]]+))?\]:\s*(.+)$');

  /// Check if text contains dialogue markup
  static bool hasDialogueMarkup(String text) {
    return RegExp(r'^\[([^\]:]+)(?::([^\]]+))?\]:').hasMatch(text);
  }

  /// Get voice ID for a speaker name (case-insensitive)
  static String? getSpeakerVoice(String speakerName) {
    // Try exact match first
    if (speakerVoiceMap.containsKey(speakerName)) {
      return speakerVoiceMap[speakerName];
    }

    // Try case-insensitive match
    final lowerName = speakerName.toLowerCase();
    for (final entry in speakerVoiceMap.entries) {
      if (entry.key.toLowerCase() == lowerName) {
        return entry.value;
      }
    }

    return null;
  }

  /// Parse dialogue markup from text into chunks
  static List<DialogueChunk> parseDialogueMarkup(String text) {
    final lines = text.trim().split('\n');
    final chunks = <DialogueChunk>[];

    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty) continue;

      final match = _markupPattern.firstMatch(trimmed);
      if (match != null) {
        final speakerOrVoice = match.group(1)!.trim();
        final emotion = match.group(2)?.trim();
        final content = match.group(3)!.trim();

        // Check if it's a voice ID (contains hyphen) or speaker name
        final voice = speakerOrVoice.contains('-')
            ? speakerOrVoice  // Direct voice ID like "en-US-GuyNeural"
            : getSpeakerVoice(speakerOrVoice);  // Map speaker name like "John"

        chunks.add(DialogueChunk(
          content: content,
          voice: voice,
          emotion: emotion,
        ));
      } else {
        // No markup detected, treat as regular text
        chunks.add(DialogueChunk(
          content: trimmed,
        ));
      }
    }

    return chunks;
  }

  /// Split regular text into chunks by sentence/punctuation
  static List<DialogueChunk> splitTextIntoChunks(String text, {String? defaultEmotion}) {
    final cleaned = text.trim();
    if (cleaned.isEmpty) return [];

    final parts = <String>[];
    
    // Split by sentence-ending punctuation
    final tokens = cleaned.split(RegExp(r'(\.{3,}|…|[.!?]|[,;]|—)'));
    var buffer = StringBuffer();
    
    for (final tok in tokens) {
      if (tok.isEmpty) continue;
      
      if (RegExp(r'^(\.{3,}|…|[.!?]|[,;]|—)$').hasMatch(tok)) {
        buffer.write(tok);
        final part = buffer.toString().trim();
        if (part.isNotEmpty) parts.add(part);
        buffer = StringBuffer();
      } else {
        if (buffer.isNotEmpty) {
          final part = buffer.toString().trim();
          if (part.isNotEmpty) parts.add(part);
          buffer = StringBuffer();
        }
        buffer.write(tok);
      }
    }
    
    if (buffer.isNotEmpty) {
      final part = buffer.toString().trim();
      if (part.isNotEmpty) parts.add(part);
    }

    // Merge tiny fragments
    final merged = <String>[];
    for (final p in parts) {
      if (merged.isNotEmpty && p.length < 15) {
        merged[merged.length - 1] = '${merged.last} $p'.trim();
      } else {
        merged.add(p);
      }
    }

    // Split overly long chunks
    final finalChunks = <String>[];
    for (final p in merged) {
      if (p.length <= 240) {
        finalChunks.add(p);
        continue;
      }
      
      final words = p.split(RegExp(r'\s+'));
      var wordBuffer = <String>[];
      
      for (final w in words) {
        final joined = [...wordBuffer, w].join(' ');
        if (joined.length > 240 && wordBuffer.isNotEmpty) {
          finalChunks.add(wordBuffer.join(' '));
          wordBuffer = [w];
        } else {
          wordBuffer.add(w);
        }
      }
      
      if (wordBuffer.isNotEmpty) {
        finalChunks.add(wordBuffer.join(' '));
      }
    }

    return finalChunks.map((c) => DialogueChunk(
      content: c,
      emotion: defaultEmotion,
    )).toList();
  }

  /// Parse text - auto-detects dialogue markup or splits into chunks
  static List<DialogueChunk> parse(String text, {String? defaultEmotion}) {
    if (hasDialogueMarkup(text)) {
      return parseDialogueMarkup(text);
    }
    return splitTextIntoChunks(text, defaultEmotion: defaultEmotion);
  }
  
  /// Get list of available speaker names
  static List<String> get availableSpeakers => speakerVoiceMap.keys.toList()..sort();
}
