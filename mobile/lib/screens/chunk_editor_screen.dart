import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import 'package:provider/provider.dart';
import '../models/dialogue_chunk.dart';
import '../models/voice.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'player_screen.dart';

class ChunkEditorScreen extends StatefulWidget {
  final List<DialogueChunk> chunks;
  final List<Voice> voices;
  final Voice globalVoice;
  final int globalRate;
  final int globalPitch;

  const ChunkEditorScreen({
    super.key,
    required this.chunks,
    required this.voices,
    required this.globalVoice,
    this.globalRate = 0,
    this.globalPitch = 0,
  });

  @override
  State<ChunkEditorScreen> createState() => _ChunkEditorScreenState();
}

class _ChunkEditorScreenState extends State<ChunkEditorScreen> {
  late List<DialogueChunk> _chunks;
  bool _isLoading = false;
  bool _autoPauses = true;
  bool _autoEmphasis = true;
  bool _autoBreaths = false;
  String? _errorMessage;
  int? _previewingIndex;
  final AudioPlayer _audioPlayer = AudioPlayer();

  @override
  void initState() {
    super.initState();
    _chunks = widget.chunks.map((c) => c.copyWith()).toList();
  }

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }

  Voice? _getVoiceByShortName(String? shortName) {
    if (shortName == null) return null;
    try {
      return widget.voices.firstWhere((v) => v.shortName == shortName);
    } catch (_) {
      return null;
    }
  }

  List<String> _getStylesForVoice(String? voiceShortName) {
    final voice = _getVoiceByShortName(voiceShortName);
    return voice?.styles ?? [];
  }

  Future<void> _generateAll() async {
    if (_chunks.isEmpty) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final apiService = context.read<ApiService>();
      final result = await apiService.synthesizeChunks(
        globalVoice: widget.globalVoice.shortName,
        chunks: _chunks,
        globalRate: widget.globalRate,
        globalPitch: widget.globalPitch,
        autoPauses: _autoPauses,
        autoEmphasis: _autoEmphasis,
        autoBreaths: _autoBreaths,
      );

      if (!mounted) return;

      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => PlayerScreen(
            audioUrl: result['audio_url'],
            text: _chunks.map((c) => c.content).join('\n'),
            voice: '${_chunks.length} speakers',
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

  void _addChunk() {
    setState(() {
      _chunks.add(DialogueChunk(content: ''));
    });
  }

  void _removeChunk(int index) {
    setState(() {
      _chunks.removeAt(index);
    });
  }

  Future<void> _previewChunk(int index) async {
    final chunk = _chunks[index];
    if (chunk.content.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter text before previewing')),
      );
      return;
    }

    setState(() => _previewingIndex = index);

    try {
      final apiService = context.read<ApiService>();
      final result = await apiService.previewChunk(
        globalVoice: widget.globalVoice.shortName,
        chunk: chunk,
        globalRate: widget.globalRate,
        globalPitch: widget.globalPitch,
      );

      if (!mounted) return;

      final audioUrl = result['audio_url'];
      if (audioUrl != null) {
        await _audioPlayer.setUrl(audioUrl);
        await _audioPlayer.play();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Preview failed: ${e.toString().replaceAll("Exception: ", "")}')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _previewingIndex = null);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Edit Chunks'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: _addChunk,
            tooltip: 'Add chunk',
          ),
        ],
      ),
      body: Column(
        children: [
          // Error message
          if (_errorMessage != null)
            Container(
              padding: const EdgeInsets.all(12),
              margin: const EdgeInsets.all(16),
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

          // Automation toggles
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                _buildToggle('Pauses', _autoPauses, (v) => setState(() => _autoPauses = v)),
                const SizedBox(width: 16),
                _buildToggle('Emphasis', _autoEmphasis, (v) => setState(() => _autoEmphasis = v)),
                const SizedBox(width: 16),
                _buildToggle('Breaths', _autoBreaths, (v) => setState(() => _autoBreaths = v)),
              ],
            ),
          ),

          const Divider(height: 1),

          // Chunk list
          Expanded(
            child: _chunks.isEmpty
                ? const Center(
                    child: Text(
                      'No chunks. Tap + to add one.',
                      style: TextStyle(color: Colors.grey),
                    ),
                  )
                : ReorderableListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _chunks.length,
                    onReorder: (oldIndex, newIndex) {
                      setState(() {
                        if (newIndex > oldIndex) newIndex--;
                        final chunk = _chunks.removeAt(oldIndex);
                        _chunks.insert(newIndex, chunk);
                      });
                    },
                    itemBuilder: (context, index) {
                      return _buildChunkCard(index);
                    },
                  ),
          ),

          // Generate button
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: ElevatedButton(
                onPressed: _isLoading || _chunks.isEmpty ? null : _generateAll,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 18),
                  minimumSize: const Size(double.infinity, 56),
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
                    : Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.play_arrow),
                          const SizedBox(width: 8),
                          Text('Generate ${_chunks.length} Chunks'),
                        ],
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildToggle(String label, bool value, ValueChanged<bool> onChanged) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: 24,
          width: 24,
          child: Checkbox(
            value: value,
            onChanged: (v) => onChanged(v ?? false),
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
          ),
        ),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 13)),
      ],
    );
  }

  Widget _buildChunkCard(int index) {
    final chunk = _chunks[index];
    final availableStyles = _getStylesForVoice(chunk.voice ?? widget.globalVoice.shortName);

    return Card(
      key: ValueKey(index),
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header with chunk number and delete
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [AppTheme.accentCoral, AppTheme.accentMint],
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    'Chunk ${index + 1}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                    ),
                  ),
                ),
                const Spacer(),
                // Preview button
                _previewingIndex == index
                    ? const SizedBox(
                        width: 24,
                        height: 24,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : IconButton(
                        icon: const Icon(Icons.play_circle_outline, color: AppTheme.accentMint),
                        onPressed: () => _previewChunk(index),
                        tooltip: 'Preview chunk',
                      ),
                IconButton(
                  icon: const Icon(Icons.drag_handle, color: Colors.grey),
                  onPressed: null,
                  tooltip: 'Drag to reorder',
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: Colors.red),
                  onPressed: () => _removeChunk(index),
                  tooltip: 'Delete chunk',
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Content textarea
            TextField(
              controller: TextEditingController(text: chunk.content),
              maxLines: 3,
              decoration: const InputDecoration(
                hintText: 'Enter text for this chunk...',
                contentPadding: EdgeInsets.all(12),
              ),
              onChanged: (value) {
                _chunks[index] = chunk.copyWith(content: value);
              },
            ),
            const SizedBox(height: 12),

            // Voice and Emotion row
            Row(
              children: [
                // Voice dropdown
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('🎙️ Voice', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                      const SizedBox(height: 4),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.grey.shade300),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String?>(
                            value: chunk.voice,
                            isExpanded: true,
                            hint: const Text('Global', style: TextStyle(fontSize: 13)),
                            items: [
                              const DropdownMenuItem(
                                value: null,
                                child: Text('Use Global Voice', style: TextStyle(fontSize: 13)),
                              ),
                              ...widget.voices.map((v) => DropdownMenuItem(
                                value: v.shortName,
                                child: Text(
                                  '${v.hasStyles ? '🎭 ' : ''}${v.displayName}',
                                  style: const TextStyle(fontSize: 13),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              )),
                            ],
                            onChanged: (value) {
                              setState(() {
                                _chunks[index] = chunk.copyWith(voice: value);
                                // Reset emotion if new voice doesn't support it
                                if (value != null) {
                                  final newStyles = _getStylesForVoice(value);
                                  if (!newStyles.contains(chunk.emotion)) {
                                    _chunks[index] = _chunks[index].copyWith(emotion: null);
                                  }
                                }
                              });
                            },
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                // Emotion dropdown
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('🎭 Emotion', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                      const SizedBox(height: 4),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.grey.shade300),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String?>(
                            value: availableStyles.contains(chunk.emotion) ? chunk.emotion : null,
                            isExpanded: true,
                            hint: const Text('Default', style: TextStyle(fontSize: 13)),
                            items: [
                              const DropdownMenuItem(
                                value: null,
                                child: Text('Default', style: TextStyle(fontSize: 13)),
                              ),
                              ...availableStyles.map((s) => DropdownMenuItem(
                                value: s,
                                child: Text(
                                  s[0].toUpperCase() + s.substring(1).replaceAll('-', ' '),
                                  style: const TextStyle(fontSize: 13),
                                ),
                              )),
                            ],
                            onChanged: availableStyles.isEmpty
                                ? null
                                : (value) {
                                    setState(() {
                                      _chunks[index] = chunk.copyWith(emotion: value);
                                    });
                                  },
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Intensity control (Speed and Pitch removed - not effective for multi-voice)
            Row(
              children: [
                _buildProsodyControl('Intensity', chunk.intensity.toDouble(), 1, 3, 2, (v) {
                  setState(() => _chunks[index] = chunk.copyWith(intensity: v.round()));
                }),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProsodyControl(
    String label,
    double value,
    double min,
    double max,
    int divisions,
    ValueChanged<double> onChanged,
  ) {
    return Expanded(
      child: Column(
        children: [
          Text(label, style: const TextStyle(fontSize: 11, color: Colors.grey)),
          Slider(
            value: value,
            min: min,
            max: max,
            divisions: divisions,
            onChanged: onChanged,
          ),
          Text(
            value == 0 ? '0' : (value > 0 ? '+${value.round()}' : '${value.round()}'),
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
