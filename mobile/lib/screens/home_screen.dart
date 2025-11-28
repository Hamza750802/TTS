import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';
import '../models/voice.dart';
import '../models/dialogue_chunk.dart';
import '../utils/dialogue_parser.dart';
import '../theme/app_theme.dart';
import 'voice_picker_screen.dart';
import 'player_screen.dart';
import 'history_screen.dart';
import 'settings_screen.dart';
import 'chunk_editor_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _textController = TextEditingController();
  Voice? _selectedVoice;
  List<Voice> _voices = [];
  bool _isLoading = false;
  bool _isLoadingVoices = true;
  double _rate = 0;
  double _pitch = 0;
  String? _selectedStyle;
  double _styleDegree = 1.0;
  bool _chunkMode = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadVoices();
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  Future<void> _loadVoices() async {
    try {
      final apiService = context.read<ApiService>();
      final authService = context.read<AuthService>();
      
      // Set session token
      if (authService.token != null) {
        apiService.setToken(authService.token!);
      }
      
      final voices = await apiService.getVoices();
      
      if (!mounted) return;
      
      setState(() {
        _voices = voices;
        _isLoadingVoices = false;
        // Set default voice (Aria)
        _selectedVoice = voices.firstWhere(
          (v) => v.shortName == 'en-US-AriaNeural',
          orElse: () => voices.first,
        );
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingVoices = false;
          _errorMessage = 'Failed to load voices';
        });
      }
    }
  }

  Future<void> _generateSpeech() async {
    if (_textController.text.trim().isEmpty) {
      setState(() => _errorMessage = 'Please enter some text');
      return;
    }
    
    if (_selectedVoice == null) {
      setState(() => _errorMessage = 'Please select a voice');
      return;
    }
    
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    
    try {
      final apiService = context.read<ApiService>();
      final result = await apiService.synthesize(
        text: _textController.text.trim(),
        voice: _selectedVoice!.shortName,
        rate: _rate.round(),
        pitch: _pitch.round(),
        style: _selectedStyle,
        styleDegree: _selectedStyle != null ? _styleDegree : null,
        chunkMode: _chunkMode,
      );
      
      if (!mounted) return;
      
      // Navigate to player
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => PlayerScreen(
            audioUrl: result['audio_url'],
            text: _textController.text.trim(),
            voice: _selectedVoice!.displayName,
          ),
        ),
      );
    } catch (e) {
      setState(() {
        _errorMessage = e.toString().replaceAll('Exception: ', '');
      });
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  void _onVoiceChanged(Voice voice) {
    setState(() {
      _selectedVoice = voice;
      // Reset style if new voice doesn't support it
      if (_selectedStyle != null && !voice.styles.contains(_selectedStyle)) {
        _selectedStyle = null;
      }
    });
  }

  void _openChunkEditor() {
    if (_selectedVoice == null) {
      setState(() => _errorMessage = 'Please select a voice first');
      return;
    }

    // Parse the text into chunks
    final text = _textController.text.trim();
    List<DialogueChunk> chunks;
    
    if (text.isEmpty) {
      // Start with empty chunk
      chunks = [DialogueChunk(content: '')];
    } else if (DialogueParser.hasDialogueMarkup(text)) {
      // Auto-parse dialogue markup
      chunks = DialogueParser.parseDialogueMarkup(text);
    } else {
      // Split text into chunks
      chunks = DialogueParser.splitTextIntoChunks(text);
    }

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ChunkEditorScreen(
          chunks: chunks,
          voices: _voices,
          globalVoice: _selectedVoice!,
          globalRate: _rate.round(),
          globalPitch: _pitch.round(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('CheapTTS'),
        leading: Padding(
          padding: const EdgeInsets.all(8.0),
          child: Container(
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [AppTheme.accentCoral, AppTheme.accentMint],
              ),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(
              Icons.record_voice_over_rounded,
              color: Colors.white,
              size: 20,
            ),
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.history),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const HistoryScreen()),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const SettingsScreen()),
              );
            },
          ),
        ],
      ),
      body: _isLoadingVoices
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Error message
                  if (_errorMessage != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: Colors.red.shade50,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.red.shade200),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.error_outline, color: Colors.red.shade700, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: TextStyle(color: Colors.red.shade700, fontSize: 14),
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.close, size: 18),
                            onPressed: () => setState(() => _errorMessage = null),
                            color: Colors.red.shade700,
                          ),
                        ],
                      ),
                    ),
                  // Text input card
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.edit_note, color: AppTheme.accentCoral),
                              const SizedBox(width: 8),
                              Text(
                                'Enter Your Text',
                                style: Theme.of(context).textTheme.titleLarge,
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          TextField(
                            controller: _textController,
                            maxLines: 6,
                            maxLength: 5000,
                            decoration: const InputDecoration(
                              hintText: 'Type or paste your text here...',
                              alignLabelWithHint: true,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  // Voice selection card
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.mic, color: AppTheme.accentMint),
                              const SizedBox(width: 8),
                              Text(
                                'Voice',
                                style: Theme.of(context).textTheme.titleLarge,
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          InkWell(
                            onTap: () async {
                              final voice = await Navigator.push<Voice>(
                                context,
                                MaterialPageRoute(
                                  builder: (_) => VoicePickerScreen(
                                    voices: _voices,
                                    selectedVoice: _selectedVoice,
                                  ),
                                ),
                              );
                              if (voice != null) {
                                _onVoiceChanged(voice);
                              }
                            },
                            borderRadius: BorderRadius.circular(14),
                            child: Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                border: Border.all(
                                  color: AppTheme.accentMint.withValues(alpha: 0.3),
                                ),
                                borderRadius: BorderRadius.circular(14),
                              ),
                              child: Row(
                                children: [
                                  Container(
                                    width: 48,
                                    height: 48,
                                    decoration: BoxDecoration(
                                      color: AppTheme.accentMint.withValues(alpha: 0.1),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: const Icon(
                                      Icons.person,
                                      color: AppTheme.accentMint,
                                    ),
                                  ),
                                  const SizedBox(width: 16),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          _selectedVoice?.displayName ?? 'Select Voice',
                                          style: const TextStyle(
                                            fontWeight: FontWeight.w600,
                                            fontSize: 16,
                                          ),
                                        ),
                                        Text(
                                          _selectedVoice != null
                                              ? '${_selectedVoice!.locale} • ${_selectedVoice!.gender}'
                                              : 'Tap to choose',
                                          style: Theme.of(context).textTheme.bodyMedium,
                                        ),
                                      ],
                                    ),
                                  ),
                                  const Icon(Icons.chevron_right),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  // Voice settings card
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.tune, color: AppTheme.accentSuccess),
                              const SizedBox(width: 8),
                              Text(
                                'Voice Settings',
                                style: Theme.of(context).textTheme.titleLarge,
                              ),
                            ],
                          ),
                          const SizedBox(height: 20),
                          // Speed slider
                          Row(
                            children: [
                              const SizedBox(width: 80, child: Text('Speed')),
                              Expanded(
                                child: Slider(
                                  value: _rate,
                                  min: -50,
                                  max: 50,
                                  divisions: 100,
                                  label: '${_rate.round()}%',
                                  onChanged: (value) => setState(() => _rate = value),
                                ),
                              ),
                              SizedBox(
                                width: 50,
                                child: Text(
                                  '${_rate.round()}%',
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ],
                          ),
                          // Pitch slider
                          Row(
                            children: [
                              const SizedBox(width: 80, child: Text('Pitch')),
                              Expanded(
                                child: Slider(
                                  value: _pitch,
                                  min: -50,
                                  max: 50,
                                  divisions: 100,
                                  label: '${_pitch.round()}%',
                                  onChanged: (value) => setState(() => _pitch = value),
                                ),
                              ),
                              SizedBox(
                                width: 50,
                                child: Text(
                                  '${_pitch.round()}%',
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ],
                          ),
                          // Reset button
                          Align(
                            alignment: Alignment.centerRight,
                            child: TextButton(
                              onPressed: () {
                                setState(() {
                                  _rate = 0;
                                  _pitch = 0;
                                });
                              },
                              child: const Text('Reset to Default'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  // Style/Emotion card (only for voices with styles)
                  if (_selectedVoice != null && _selectedVoice!.hasStyles)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.emoji_emotions, color: AppTheme.accentCoral),
                                const SizedBox(width: 8),
                                Text(
                                  'Emotion / Style',
                                  style: Theme.of(context).textTheme.titleLarge,
                                ),
                              ],
                            ),
                            const SizedBox(height: 16),
                            // Style dropdown
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12),
                              decoration: BoxDecoration(
                                border: Border.all(color: AppTheme.accentCoral.withValues(alpha: 0.3)),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: DropdownButtonHideUnderline(
                                child: DropdownButton<String?>(
                                  value: _selectedStyle,
                                  isExpanded: true,
                                  hint: const Text('Select style (optional)'),
                                  items: [
                                    const DropdownMenuItem<String?>(
                                      value: null,
                                      child: Text('No style (neutral)'),
                                    ),
                                    ..._selectedVoice!.styles.map((style) {
                                      return DropdownMenuItem(
                                        value: style,
                                        child: Text(style.replaceAll('-', ' ').split(' ').map((w) => 
                                          w.isNotEmpty ? w[0].toUpperCase() + w.substring(1) : w
                                        ).join(' ')),
                                      );
                                    }),
                                  ],
                                  onChanged: (value) => setState(() => _selectedStyle = value),
                                ),
                              ),
                            ),
                            // Style intensity slider (only when style selected)
                            if (_selectedStyle != null) ...[
                              const SizedBox(height: 16),
                              Row(
                                children: [
                                  const SizedBox(width: 80, child: Text('Intensity')),
                                  Expanded(
                                    child: Slider(
                                      value: _styleDegree,
                                      min: 0.5,
                                      max: 1.5,
                                      divisions: 10,
                                      label: _styleDegree == 1.0 ? 'Normal' : 
                                             _styleDegree < 1.0 ? 'Subtle' : 'Strong',
                                      onChanged: (value) => setState(() => _styleDegree = value),
                                    ),
                                  ),
                                  SizedBox(
                                    width: 60,
                                    child: Text(
                                      _styleDegree == 1.0 ? 'Normal' : 
                                      _styleDegree < 1.0 ? 'Subtle' : 'Strong',
                                      textAlign: TextAlign.center,
                                      style: const TextStyle(fontSize: 12),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  if (_selectedVoice != null && _selectedVoice!.hasStyles)
                    const SizedBox(height: 16),
                  // Advanced Options card
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.settings_suggest, color: Colors.grey),
                              const SizedBox(width: 8),
                              Text(
                                'Advanced Options',
                                style: Theme.of(context).textTheme.titleLarge,
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          // Chunk mode toggle
                          SwitchListTile(
                            title: const Text('Split Long Text'),
                            subtitle: const Text('Better quality for text >1000 chars'),
                            value: _chunkMode,
                            onChanged: (value) => setState(() => _chunkMode = value),
                            contentPadding: EdgeInsets.zero,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  // Multi-Speaker Dialogue Card
                  Card(
                    child: InkWell(
                      onTap: _openChunkEditor,
                      borderRadius: BorderRadius.circular(14),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(10),
                                  decoration: BoxDecoration(
                                    gradient: const LinearGradient(
                                      colors: [AppTheme.accentCoral, AppTheme.accentMint],
                                    ),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: const Icon(
                                    Icons.people_alt_rounded,
                                    color: Colors.white,
                                    size: 24,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        'Multi-Speaker Dialogue',
                                        style: Theme.of(context).textTheme.titleLarge,
                                      ),
                                      Text(
                                        'Different voices & emotions per chunk',
                                        style: Theme.of(context).textTheme.bodySmall,
                                      ),
                                    ],
                                  ),
                                ),
                                const Icon(Icons.chevron_right, color: Colors.grey),
                              ],
                            ),
                            const SizedBox(height: 12),
                            // Dialogue markup hint
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: AppTheme.accentMint.withValues(alpha: 0.1),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    '💡 Tip: Use dialogue markup for quick setup:',
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                      color: AppTheme.accentMint.withValues(alpha: 0.8),
                                    ),
                                  ),
                                  const SizedBox(height: 6),
                                  Text(
                                    '[Jenny]: Hello, how are you?\n[Guy:cheerful]: I\'m doing great!',
                                    style: TextStyle(
                                      fontSize: 11,
                                      fontFamily: 'monospace',
                                      color: Colors.grey.shade600,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  // Generate button
                  ElevatedButton(
                    onPressed: _isLoading ? null : _generateSpeech,
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 18),
                    ),
                    child: _isLoading
                        ? const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                ),
                              ),
                              SizedBox(width: 12),
                              Text('Generating...'),
                            ],
                          )
                        : const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.play_arrow),
                              SizedBox(width: 8),
                              Text('Generate Speech'),
                            ],
                          ),
                  ),
                  const SizedBox(height: 20),
                ],
              ),
            ),
    );
  }
}
