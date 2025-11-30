import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
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
      final authService = context.read<AuthService>();
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
      
      // Update character usage from response
      if (result['chars_remaining'] != null) {
        await authService.updateCharUsage(
          charsUsed: (authService.charsLimit - (result['chars_remaining'] as int)),
          charsRemaining: result['chars_remaining'] as int,
          charsLimit: result['chars_limit'] as int?,
        );
      }
      
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
      final errorStr = e.toString().replaceAll('Exception: ', '');
      
      // Check if it's a character limit error
      if (errorStr.contains('limit reached') || errorStr.contains('Character limit')) {
        _showUpgradeDialog();
      } else {
        setState(() {
          _errorMessage = errorStr;
        });
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }
  
  void _showUpgradeDialog() {
    final authService = context.read<AuthService>();
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [AppTheme.accentCoral, Color(0xFFFF8E53)]),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(Icons.star, color: Colors.white, size: 20),
            ),
            const SizedBox(width: 12),
            const Text('Go Unlimited'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.orange.shade200),
              ),
              child: Row(
                children: [
                  Icon(Icons.info_outline, color: Colors.orange.shade700, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'You\'ve used ${_formatNumber(authService.charsUsed.toInt())} of ${_formatNumber(authService.charsLimit.toInt())} characters.',
                      style: TextStyle(fontSize: 13, color: Colors.orange.shade800),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            // Pricing
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Column(
                  children: [
                    const Text(
                      '\$7.99',
                      style: TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.accentCoral,
                      ),
                    ),
                    Text(
                      'per month',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                    ),
                  ],
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text('or', style: TextStyle(color: Colors.grey.shade500)),
                ),
                Column(
                  children: [
                    const Text(
                      '\$99',
                      style: TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.accentMint,
                      ),
                    ),
                    Text(
                      'lifetime',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 20),
            const Text(
              'Unlimited includes:',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
            ),
            const SizedBox(height: 10),
            _buildFeatureRow(Icons.all_inclusive, 'Unlimited characters forever'),
            _buildFeatureRow(Icons.speed, 'Priority audio generation'),
            _buildFeatureRow(Icons.business, 'Commercial use rights'),
            _buildFeatureRow(Icons.support_agent, 'Email support'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Later', style: TextStyle(color: Colors.grey.shade600)),
          ),
          Container(
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: [AppTheme.accentCoral, Color(0xFFFF8E53)]),
              borderRadius: BorderRadius.circular(10),
              boxShadow: [
                BoxShadow(
                  color: AppTheme.accentCoral.withAlpha(77),
                  blurRadius: 8,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () async {
                  Navigator.pop(context);
                  final url = Uri.parse('https://cheaptts.com/subscribe');
                  if (await canLaunchUrl(url)) {
                    await launchUrl(url, mode: LaunchMode.externalApplication);
                  }
                },
                borderRadius: BorderRadius.circular(10),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  child: Text(
                    'Upgrade Now',
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
  
  Widget _buildFeatureRow(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Icon(icon, color: AppTheme.accentSuccess, size: 18),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
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
  
  String _formatNumber(int number) {
    if (number >= 1000000) {
      return '${(number / 1000000).toStringAsFixed(1)}M';
    } else if (number >= 1000) {
      return '${(number / 1000).toStringAsFixed(1)}K';
    }
    return number.toString().replaceAllMapped(
      RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'),
      (m) => '${m[1]},',
    );
  }

  @override
  Widget build(BuildContext context) {
    final authService = context.watch<AuthService>();
    final usagePercent = authService.usagePercent;
    
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
                  // Character usage card
                  Card(
                    margin: const EdgeInsets.only(bottom: 16),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    usagePercent >= 100 
                                        ? Icons.error 
                                        : usagePercent >= 80 
                                            ? Icons.warning 
                                            : Icons.analytics,
                                    color: usagePercent >= 100
                                        ? Colors.red
                                        : usagePercent >= 80
                                            ? Colors.orange
                                            : AppTheme.accentCoral,
                                    size: 20,
                                  ),
                                  const SizedBox(width: 8),
                                  Text(
                                    'Monthly Usage',
                                    style: Theme.of(context).textTheme.titleMedium,
                                  ),
                                  const SizedBox(width: 8),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                    decoration: BoxDecoration(
                                      gradient: authService.charsLimit >= 999999999
                                          ? const LinearGradient(colors: [AppTheme.accentMint, Color(0xFF7EC8E3)])
                                          : null,
                                      color: authService.charsLimit >= 999999999 ? null : AppTheme.accentCoral.withAlpha(25),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Text(
                                      authService.charsLimit >= 999999999 ? 'UNLIMITED' : 'FREE',
                                      style: TextStyle(
                                        fontSize: 10,
                                        fontWeight: FontWeight.bold,
                                        color: authService.charsLimit >= 999999999 ? Colors.white : AppTheme.accentCoral,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              Text(
                                authService.charsLimit >= 999999999
                                    ? '∞ Unlimited'
                                    : '${_formatNumber(authService.charsUsed.toInt())} / ${_formatNumber(authService.charsLimit.toInt())}',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  color: usagePercent >= 100
                                      ? Colors.red
                                      : usagePercent >= 80
                                          ? Colors.orange
                                          : Colors.grey.shade700,
                                ),
                              ),
                            ],
                          ),
                          if (authService.charsLimit < 999999999) ...[
                            const SizedBox(height: 12),
                            ClipRRect(
                              borderRadius: BorderRadius.circular(8),
                              child: LinearProgressIndicator(
                                value: (usagePercent / 100).clamp(0.0, 1.0),
                                minHeight: 10,
                                backgroundColor: Colors.grey.shade200,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  usagePercent >= 100
                                      ? Colors.red
                                      : usagePercent >= 80
                                          ? Colors.orange
                                          : AppTheme.accentCoral,
                                ),
                              ),
                            ),
                            const SizedBox(height: 8),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  '${_formatNumber(authService.charsRemaining.toInt())} characters left',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Colors.grey.shade600,
                                  ),
                                ),
                                Text(
                                  'Resets monthly',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Colors.grey.shade500,
                                  ),
                                ),
                              ],
                            ),
                          ] else ...[
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                Icon(Icons.check_circle, color: AppTheme.accentSuccess, size: 16),
                                const SizedBox(width: 6),
                                Text(
                                  'You have unlimited characters with your subscription',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: AppTheme.accentSuccess,
                                  ),
                                ),
                              ],
                            ),
                          ],
                          if (authService.charsLimit < 999999999 && usagePercent >= 50) ...[
                            const SizedBox(height: 12),
                            Container(
                              width: double.infinity,
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  colors: usagePercent >= 100
                                      ? [Colors.red.shade400, Colors.red.shade600]
                                      : usagePercent >= 80
                                          ? [Colors.orange.shade400, Colors.orange.shade600]
                                          : [AppTheme.accentCoral.withAlpha(204), AppTheme.accentCoral],
                                ),
                                borderRadius: BorderRadius.circular(12),
                                boxShadow: [
                                  BoxShadow(
                                    color: (usagePercent >= 100 ? Colors.red : usagePercent >= 80 ? Colors.orange : AppTheme.accentCoral).withAlpha(77),
                                    blurRadius: 8,
                                    offset: const Offset(0, 4),
                                  ),
                                ],
                              ),
                              child: Material(
                                color: Colors.transparent,
                                child: InkWell(
                                  onTap: _showUpgradeDialog,
                                  borderRadius: BorderRadius.circular(12),
                                  child: Padding(
                                    padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        const Icon(Icons.star, color: Colors.white, size: 18),
                                        const SizedBox(width: 8),
                                        Text(
                                          usagePercent >= 100
                                              ? 'Upgrade for Unlimited - \$7.99/mo'
                                              : usagePercent >= 80
                                                  ? 'Running Low! Upgrade Now'
                                                  : 'Go Unlimited - \$7.99/mo',
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontWeight: FontWeight.bold,
                                            fontSize: 14,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),

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

                  // Multi-speaker dialogue instructions
                  Card(
                    margin: const EdgeInsets.only(bottom: 16),
                    color: Colors.blue.shade50,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(Icons.people, color: Colors.blue.shade700, size: 20),
                              const SizedBox(width: 8),
                              Text(
                                'Multi-Speaker Dialogue',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  color: Colors.blue.shade700,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Create conversations with different voices:',
                            style: TextStyle(
                              fontSize: 13,
                              color: Colors.blue.shade900,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: Colors.blue.shade200),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Example:',
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 12,
                                    color: Colors.blue.shade700,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                const Text(
                                  '[John]: Hello, how are you today?\n[Sarah]: I\'m doing great, thanks!',
                                  style: TextStyle(
                                    fontFamily: 'monospace',
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 10),
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: Colors.blue.shade700,
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: const Text(
                                  '1',
                                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                              ),
                              const SizedBox(width: 8),
                              const Expanded(
                                child: Text(
                                  'Use [Name]: format for each speaker',
                                  style: TextStyle(fontSize: 12),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: Colors.blue.shade700,
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: const Text(
                                  '2',
                                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Row(
                                  children: [
                                    const Text(
                                      'Tap ',
                                      style: TextStyle(fontSize: 12),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: Colors.grey.shade200,
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                      child: const Text(
                                        'Split into Chunks',
                                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
                                      ),
                                    ),
                                    const Text(
                                      ' button',
                                      style: TextStyle(fontSize: 12),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: Colors.blue.shade700,
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: const Text(
                                  '3',
                                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                              ),
                              const SizedBox(width: 8),
                              const Expanded(
                                child: Text(
                                  'Assign different voices to each speaker',
                                  style: TextStyle(fontSize: 12),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: Colors.blue.shade700,
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: const Text(
                                  '4',
                                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                              ),
                              const SizedBox(width: 8),
                              const Expanded(
                                child: Text(
                                  'Generate to create dialogue audio',
                                  style: TextStyle(fontSize: 12),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
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
