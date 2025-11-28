// Basic widget test for CheapTTS Mobile
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    // Simple smoke test
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: Text('CheapTTS Mobile'),
          ),
        ),
      ),
    );

    expect(find.text('CheapTTS Mobile'), findsOneWidget);
  });
}
