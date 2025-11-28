import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/auth_service.dart';
import '../theme/app_theme.dart';
import 'login_screen.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final authService = context.watch<AuthService>();
    
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Account section
          _SectionHeader(title: 'Account'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: CircleAvatar(
                    backgroundColor: AppTheme.accentCoral.withValues(alpha: 0.1),
                    child: const Icon(Icons.person, color: AppTheme.accentCoral),
                  ),
                  title: Text(authService.email ?? 'Not logged in'),
                  subtitle: const Text('Email'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: CircleAvatar(
                    backgroundColor: AppTheme.accentMint.withValues(alpha: 0.1),
                    child: const Icon(Icons.card_membership, color: AppTheme.accentMint),
                  ),
                  title: Text(_formatSubscription(authService.subscriptionStatus)),
                  subtitle: const Text('Web Subscription'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: CircleAvatar(
                    backgroundColor: AppTheme.accentSuccess.withValues(alpha: 0.1),
                    child: const Icon(Icons.api, color: AppTheme.accentSuccess),
                  ),
                  title: Text(_formatApiTier(authService.apiTier)),
                  subtitle: const Text('API Plan'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // Subscription section
          _SectionHeader(title: 'Subscription'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.upgrade, color: AppTheme.accentCoral),
                  title: const Text('Upgrade Plan'),
                  subtitle: const Text('Get unlimited access'),
                  trailing: const Icon(Icons.open_in_new),
                  onTap: () => _launchUrl('https://cheaptts.com/subscribe'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.code, color: AppTheme.accentMint),
                  title: const Text('API Access'),
                  subtitle: const Text('View API plans'),
                  trailing: const Icon(Icons.open_in_new),
                  onTap: () => _launchUrl('https://cheaptts.com/api-pricing'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // Support section
          _SectionHeader(title: 'Support'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.help_outline),
                  title: const Text('Help & FAQ'),
                  trailing: const Icon(Icons.open_in_new),
                  onTap: () => _launchUrl('https://cheaptts.com'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.mail_outline),
                  title: const Text('Contact Support'),
                  trailing: const Icon(Icons.open_in_new),
                  onTap: () => _launchUrl('mailto:support@cheaptts.com'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.privacy_tip_outlined),
                  title: const Text('Privacy Policy'),
                  trailing: const Icon(Icons.open_in_new),
                  onTap: () => _launchUrl('https://cheaptts.com/privacy'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.description_outlined),
                  title: const Text('Terms of Service'),
                  trailing: const Icon(Icons.open_in_new),
                  onTap: () => _launchUrl('https://cheaptts.com/terms'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // About section
          _SectionHeader(title: 'About'),
          Card(
            child: Column(
              children: [
                const ListTile(
                  leading: Icon(Icons.info_outline),
                  title: Text('Version'),
                  trailing: Text('1.0.0'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.star_outline),
                  title: const Text('Rate the App'),
                  trailing: const Icon(Icons.open_in_new),
                  onTap: () {
                    // TODO: Add store links
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 32),
          // Logout button
          ElevatedButton.icon(
            onPressed: () => _logout(context),
            icon: const Icon(Icons.logout),
            label: const Text('Sign Out'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red.shade50,
              foregroundColor: Colors.red,
              padding: const EdgeInsets.symmetric(vertical: 16),
            ),
          ),
          const SizedBox(height: 32),
          // Footer
          Center(
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [AppTheme.accentCoral, AppTheme.accentMint],
                        ),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(
                        Icons.record_voice_over_rounded,
                        color: Colors.white,
                        size: 18,
                      ),
                    ),
                    const SizedBox(width: 8),
                    const Text(
                      'CheapTTS',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 16,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  'Text to Speech, Made Simple',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  String _formatSubscription(String? status) {
    switch (status) {
      case 'active':
        return '✅ Active';
      case 'lifetime':
        return '⭐ Lifetime';
      case 'past_due':
        return '⚠️ Past Due';
      case 'canceled':
        return '❌ Canceled';
      default:
        return '🆓 Free';
    }
  }

  String _formatApiTier(String? tier) {
    switch (tier) {
      case 'starter':
        return '🚀 Starter (100k chars/mo)';
      case 'pro':
        return '💼 Pro (500k chars/mo)';
      case 'enterprise':
        return '🏢 Enterprise';
      default:
        return 'No API access';
    }
  }

  Future<void> _launchUrl(String url) async {
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  Future<void> _logout(BuildContext context) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sign Out'),
        content: const Text('Are you sure you want to sign out?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Sign Out'),
          ),
        ],
      ),
    );
    
    if (confirm == true && context.mounted) {
      final authService = context.read<AuthService>();
      await authService.logout();
      
      if (context.mounted) {
        Navigator.pushAndRemoveUntil(
          context,
          MaterialPageRoute(builder: (_) => const LoginScreen()),
          (route) => false,
        );
      }
    }
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;

  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 8),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: AppTheme.textMuted,
          letterSpacing: 1,
        ),
      ),
    );
  }
}
