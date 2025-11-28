class Voice {
  final String name;
  final String shortName;
  final String gender;
  final String locale;
  final String localName;
  final List<String> styles;
  final bool hasStyles;
  
  Voice({
    required this.name,
    required this.shortName,
    required this.gender,
    required this.locale,
    required this.localName,
    this.styles = const [],
    this.hasStyles = false,
  });
  
  factory Voice.fromJson(Map<String, dynamic> json) {
    return Voice(
      name: json['name'] ?? '',
      shortName: json['shortName'] ?? '',
      gender: json['gender'] ?? '',
      locale: json['locale'] ?? '',
      localName: json['localName'] ?? '',
      styles: json['styles'] != null 
          ? List<String>.from(json['styles']) 
          : [],
      hasStyles: json['has_styles'] ?? false,
    );
  }
  
  String get displayName {
    // Use localName if available, otherwise extract from shortName
    if (localName.isNotEmpty) {
      return localName;
    }
    // Extract friendly name: "en-US-AriaNeural" -> "Aria"
    final parts = shortName.split('-');
    if (parts.length >= 3) {
      return parts[2].replaceAll('Neural', '');
    }
    return name;
  }
  
  String get languageCode => locale.split('-').first;
}
