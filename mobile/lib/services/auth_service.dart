import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AuthService extends ChangeNotifier {
  String? _email;
  String? _token;  // Session token from login
  String? _subscriptionStatus;
  String? _apiTier;
  int _charsUsed = 0;
  int _charsLimit = 10000;
  int _charsRemaining = 10000;
  bool _isLoading = true;
  
  String? get email => _email;
  String? get token => _token;  // Session token
  String? get subscriptionStatus => _subscriptionStatus;
  String? get apiTier => _apiTier;
  int get charsUsed => _charsUsed;
  int get charsLimit => _charsLimit;
  int get charsRemaining => _charsRemaining;
  bool get isLoading => _isLoading;
  bool get isLoggedIn => _email != null && _token != null;
  bool get hasWebAccess => _subscriptionStatus == 'active' || _subscriptionStatus == 'lifetime';
  bool get hasApiAccess => _apiTier != null && _apiTier != 'none';
  bool get isUnlimited => hasWebAccess;  // Subscribers have unlimited chars
  
  // Usage percentage (0-100+)
  double get usagePercent => _charsLimit > 0 ? (_charsUsed / _charsLimit) * 100 : 0;
  // Check if user is near limit (>80% used)
  bool get isNearLimit => !isUnlimited && _charsUsed > (_charsLimit * 0.8);
  // Check if limit is reached
  bool get isLimitReached => !isUnlimited && _charsRemaining <= 0;
  
  AuthService() {
    _loadSavedAuth();
  }
  
  Future<void> _loadSavedAuth() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _email = prefs.getString('email');
      _token = prefs.getString('token');
      _subscriptionStatus = prefs.getString('subscription_status');
      _apiTier = prefs.getString('api_tier');
      _charsUsed = prefs.getInt('chars_used') ?? 0;
      _charsLimit = prefs.getInt('chars_limit') ?? 10000;
      _charsRemaining = prefs.getInt('chars_remaining') ?? 10000;
    } catch (e) {
      // Ignore errors on load
    }
    _isLoading = false;
    notifyListeners();
  }
  
  Future<void> login({
    required String email,
    required String token,
    String? subscriptionStatus,
    String? apiTier,
    int? charsUsed,
    int? charsLimit,
    int? charsRemaining,
  }) async {
    _email = email;
    _token = token;
    _subscriptionStatus = subscriptionStatus;
    _apiTier = apiTier;
    _charsUsed = charsUsed ?? 0;
    _charsLimit = charsLimit ?? 10000;
    _charsRemaining = charsRemaining ?? 10000;
    
    // Save to local storage
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('email', email);
    await prefs.setString('token', token);
    if (subscriptionStatus != null) {
      await prefs.setString('subscription_status', subscriptionStatus);
    }
    if (apiTier != null) {
      await prefs.setString('api_tier', apiTier);
    }
    await prefs.setInt('chars_used', _charsUsed);
    await prefs.setInt('chars_limit', _charsLimit);
    await prefs.setInt('chars_remaining', _charsRemaining);
    
    notifyListeners();
  }
  
  Future<void> logout() async {
    _email = null;
    _token = null;
    _subscriptionStatus = null;
    _apiTier = null;
    _charsUsed = 0;
    _charsLimit = 10000;
    _charsRemaining = 10000;
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('email');
    await prefs.remove('token');
    await prefs.remove('subscription_status');
    await prefs.remove('api_tier');
    await prefs.remove('chars_used');
    await prefs.remove('chars_limit');
    await prefs.remove('chars_remaining');
    
    notifyListeners();
  }
  
  Future<void> updateSubscription({
    String? subscriptionStatus,
    String? apiTier,
  }) async {
    if (subscriptionStatus != null) _subscriptionStatus = subscriptionStatus;
    if (apiTier != null) _apiTier = apiTier;
    
    final prefs = await SharedPreferences.getInstance();
    if (subscriptionStatus != null) {
      await prefs.setString('subscription_status', subscriptionStatus);
    }
    if (apiTier != null) {
      await prefs.setString('api_tier', apiTier);
    }
    
    notifyListeners();
  }
  
  /// Update character usage from API response
  Future<void> updateCharUsage({
    required int charsUsed,
    required int charsRemaining,
    int? charsLimit,
  }) async {
    _charsUsed = charsUsed;
    _charsRemaining = charsRemaining;
    if (charsLimit != null) _charsLimit = charsLimit;
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('chars_used', _charsUsed);
    await prefs.setInt('chars_remaining', _charsRemaining);
    if (charsLimit != null) {
      await prefs.setInt('chars_limit', _charsLimit);
    }
    
    notifyListeners();
  }
}
