/// Represents a single chunk in a multi-speaker dialogue
class DialogueChunk {
  String content;
  String? voice;       // Override voice for this chunk (null = use global)
  String? emotion;     // Style/emotion (cheerful, sad, angry, etc.)
  int intensity;       // 1-3 scale for emotion intensity
  int speed;           // -50 to +50 percent
  int pitch;           // -50 to +50 percent
  int volume;          // -50 to +50 percent
  
  DialogueChunk({
    required this.content,
    this.voice,
    this.emotion,
    this.intensity = 2,
    this.speed = 0,
    this.pitch = 0,
    this.volume = 0,
  });
  
  Map<String, dynamic> toJson() => {
    'content': content,
    if (voice != null) 'voice': voice,
    if (emotion != null) 'emotion': emotion,
    'intensity': intensity,
    'speed': speed,
    'pitch': pitch,
    'volume': volume,
  };
  
  factory DialogueChunk.fromJson(Map<String, dynamic> json) => DialogueChunk(
    content: json['content'] ?? '',
    voice: json['voice'],
    emotion: json['emotion'],
    intensity: json['intensity'] ?? 2,
    speed: json['speed'] ?? 0,
    pitch: json['pitch'] ?? 0,
    volume: json['volume'] ?? 0,
  );
  
  DialogueChunk copyWith({
    String? content,
    String? voice,
    String? emotion,
    int? intensity,
    int? speed,
    int? pitch,
    int? volume,
  }) => DialogueChunk(
    content: content ?? this.content,
    voice: voice ?? this.voice,
    emotion: emotion ?? this.emotion,
    intensity: intensity ?? this.intensity,
    speed: speed ?? this.speed,
    pitch: pitch ?? this.pitch,
    volume: volume ?? this.volume,
  );
}
