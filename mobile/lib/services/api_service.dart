import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/voice.dart';
import '../models/dialogue_chunk.dart';

class ApiService {
  static const String baseUrl = 'https://cheaptts.com';
  
  String? _token;  // Session token for mobile API
  
  void setToken(String token) {
    _token = token;
  }
  
  void clearToken() {
    _token = null;
  }
  
  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (_token != null) 'Authorization': 'Bearer $_token',
  };
  
  // Login and get user info
  Future<Map<String, dynamic>> login(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      final error = jsonDecode(response.body);
      throw Exception(error['error'] ?? 'Login failed');
    }
  }
  
  // Register new user
  Future<Map<String, dynamic>> register(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/signup'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    
    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body);
    } else {
      final error = jsonDecode(response.body);
      throw Exception(error['error'] ?? 'Registration failed');
    }
  }
  
  // Request password reset
  Future<void> forgotPassword(String email) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/forgot-password'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email}),
    );
    
    if (response.statusCode != 200) {
      final error = jsonDecode(response.body);
      throw Exception(error['error'] ?? 'Request failed');
    }
  }
  
  // Get available voices
  Future<List<Voice>> getVoices() async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/voices'),
      headers: _headers,
    );
    
    if (response.statusCode == 200) {
      final Map<String, dynamic> data = jsonDecode(response.body);
      final List<dynamic> voices = data['voices'] ?? [];
      return voices.map((json) => Voice.fromJson(json)).toList();
    } else {
      throw Exception('Failed to load voices');
    }
  }
  
  // Synthesize text to speech (mobile endpoint with session token)
  Future<Map<String, dynamic>> synthesize({
    required String text,
    required String voice,
    int? rate,
    int? pitch,
    String? style,
    double? styleDegree,
    bool chunkMode = false,
  }) async {
    final body = {
      'text': text,
      'voice': voice,
      if (rate != null) 'rate': rate,
      if (pitch != null) 'pitch': pitch,
      if (style != null) 'style': style,
      if (styleDegree != null) 'style_degree': styleDegree,
      if (chunkMode) 'chunk_mode': true,
    };
    
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/mobile/synthesize'),
      headers: _headers,
      body: jsonEncode(body),
    );
    
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      final error = jsonDecode(response.body);
      throw Exception(error['error'] ?? 'Synthesis failed');
    }
  }
  
  // Synthesize multi-speaker dialogue chunks
  Future<Map<String, dynamic>> synthesizeChunks({
    required String globalVoice,
    required List<DialogueChunk> chunks,
    int globalRate = 0,
    int globalPitch = 0,
    int globalVolume = 0,
    bool autoPauses = true,
    bool autoEmphasis = true,
    bool autoBreaths = false,
  }) async {
    final body = {
      'voice': globalVoice,
      'chunks': chunks.map((c) => c.toJson()).toList(),
      'global_controls': {
        'rate': globalRate,
        'pitch': globalPitch,
        'volume': globalVolume ~/ 5,  // Convert to dB scale like web
      },
      'auto_pauses': autoPauses,
      'auto_emphasis': autoEmphasis,
      'auto_breaths': autoBreaths,
    };
    
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/mobile/synthesize'),
      headers: _headers,
      body: jsonEncode(body),
    );
    
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      final error = jsonDecode(response.body);
      throw Exception(error['error'] ?? 'Synthesis failed');
    }
  }
  
  // Preview a single chunk
  Future<Map<String, dynamic>> previewChunk({
    required String globalVoice,
    required DialogueChunk chunk,
    int globalRate = 0,
    int globalPitch = 0,
    int globalVolume = 0,
  }) async {
    final body = {
      'voice': globalVoice,
      'chunk': chunk.toJson(),
      'global_pitch': globalPitch,
      'global_rate': globalRate,
      'global_volume': globalVolume ~/ 5,
    };
    
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/mobile/preview'),
      headers: _headers,
      body: jsonEncode(body),
    );
    
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      final error = jsonDecode(response.body);
      throw Exception(error['error'] ?? 'Preview failed');
    }
  }
  
  // Get user's API usage
  Future<Map<String, dynamic>> getUsage() async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/v1/usage'),
      headers: _headers,
    );
    
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception('Failed to get usage');
    }
  }
  
  // Logout (invalidate session)
  Future<void> logout() async {
    await http.post(
      Uri.parse('$baseUrl/api/v1/auth/logout'),
      headers: _headers,
    );
    clearToken();
  }
}
