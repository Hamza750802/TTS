class GenerationHistory {
  final String id;
  final String text;
  final String voice;
  final String audioUrl;
  final DateTime createdAt;
  
  GenerationHistory({
    required this.id,
    required this.text,
    required this.voice,
    required this.audioUrl,
    required this.createdAt,
  });
  
  factory GenerationHistory.fromJson(Map<String, dynamic> json) {
    return GenerationHistory(
      id: json['id'] ?? DateTime.now().millisecondsSinceEpoch.toString(),
      text: json['text'] ?? '',
      voice: json['voice'] ?? '',
      audioUrl: json['audio_url'] ?? '',
      createdAt: json['created_at'] != null 
          ? DateTime.parse(json['created_at']) 
          : DateTime.now(),
    );
  }
  
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'text': text,
      'voice': voice,
      'audio_url': audioUrl,
      'created_at': createdAt.toIso8601String(),
    };
  }
  
  String get shortText {
    if (text.length <= 50) return text;
    return '${text.substring(0, 50)}...';
  }
}
