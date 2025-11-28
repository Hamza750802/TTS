import 'package:flutter/material.dart';
import '../models/voice.dart';
import '../theme/app_theme.dart';

class VoicePickerScreen extends StatefulWidget {
  final List<Voice> voices;
  final Voice? selectedVoice;

  const VoicePickerScreen({
    super.key,
    required this.voices,
    this.selectedVoice,
  });

  @override
  State<VoicePickerScreen> createState() => _VoicePickerScreenState();
}

class _VoicePickerScreenState extends State<VoicePickerScreen> {
  final _searchController = TextEditingController();
  String _searchQuery = '';
  String _selectedLanguage = 'All';
  String _selectedGender = 'All';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<Voice> get _filteredVoices {
    return widget.voices.where((voice) {
      // Search filter
      if (_searchQuery.isNotEmpty) {
        final query = _searchQuery.toLowerCase();
        if (!voice.displayName.toLowerCase().contains(query) &&
            !voice.locale.toLowerCase().contains(query) &&
            !voice.localName.toLowerCase().contains(query)) {
          return false;
        }
      }
      
      // Language filter
      if (_selectedLanguage != 'All' && voice.languageCode != _selectedLanguage) {
        return false;
      }
      
      // Gender filter
      if (_selectedGender != 'All' && voice.gender != _selectedGender) {
        return false;
      }
      
      return true;
    }).toList();
  }

  List<String> get _availableLanguages {
    final languages = widget.voices.map((v) => v.languageCode).toSet().toList();
    languages.sort();
    return ['All', ...languages];
  }

  @override
  Widget build(BuildContext context) {
    final filteredVoices = _filteredVoices;
    
    return Scaffold(
      appBar: AppBar(
        title: const Text('Select Voice'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(60),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search voices...',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchController.clear();
                          setState(() => _searchQuery = '');
                        },
                      )
                    : null,
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              ),
              onChanged: (value) => setState(() => _searchQuery = value),
            ),
          ),
        ),
      ),
      body: Column(
        children: [
          // Filters
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                // Language filter
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    decoration: BoxDecoration(
                      border: Border.all(color: AppTheme.accentMint.withValues(alpha: 0.3)),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<String>(
                        value: _selectedLanguage,
                        isExpanded: true,
                        hint: const Text('Language'),
                        items: _availableLanguages.map((lang) {
                          return DropdownMenuItem(
                            value: lang,
                            child: Text(lang == 'All' ? 'All Languages' : lang.toUpperCase()),
                          );
                        }).toList(),
                        onChanged: (value) {
                          if (value != null) setState(() => _selectedLanguage = value);
                        },
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                // Gender filter
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    decoration: BoxDecoration(
                      border: Border.all(color: AppTheme.accentMint.withValues(alpha: 0.3)),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<String>(
                        value: _selectedGender,
                        isExpanded: true,
                        items: ['All', 'Male', 'Female'].map((gender) {
                          return DropdownMenuItem(
                            value: gender,
                            child: Text(gender == 'All' ? 'All Genders' : gender),
                          );
                        }).toList(),
                        onChanged: (value) {
                          if (value != null) setState(() => _selectedGender = value);
                        },
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          // Results count
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                Text(
                  '${filteredVoices.length} voices',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ),
          ),
          // Voice list
          Expanded(
            child: ListView.builder(
              itemCount: filteredVoices.length,
              itemBuilder: (context, index) {
                final voice = filteredVoices[index];
                final isSelected = widget.selectedVoice?.shortName == voice.shortName;
                
                return ListTile(
                  onTap: () => Navigator.pop(context, voice),
                  leading: Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: isSelected
                          ? AppTheme.accentCoral.withValues(alpha: 0.1)
                          : AppTheme.accentMint.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(
                      voice.gender == 'Male' ? Icons.male : Icons.female,
                      color: isSelected ? AppTheme.accentCoral : AppTheme.accentMint,
                    ),
                  ),
                  title: Row(
                    children: [
                      Text(
                        voice.displayName,
                        style: TextStyle(
                          fontWeight: isSelected ? FontWeight.w700 : FontWeight.w600,
                          color: isSelected ? AppTheme.accentCoral : null,
                        ),
                      ),
                      if (voice.hasStyles) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppTheme.accentSuccess.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            '🎭',
                            style: TextStyle(fontSize: 10),
                          ),
                        ),
                      ],
                    ],
                  ),
                  subtitle: Text(
                    '${voice.locale} • ${voice.gender}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  trailing: isSelected
                      ? const Icon(Icons.check_circle, color: AppTheme.accentCoral)
                      : const Icon(Icons.chevron_right),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
