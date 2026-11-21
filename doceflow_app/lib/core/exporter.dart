import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

/// Exporta um arquivo pela janela de compartilhar do Android (salvar em Arquivos, Drive,
/// WhatsApp, Instagram...). Trocável nos testes.
abstract interface class FileExporter {
  Future<void> exportPng(Uint8List bytes, String fileName);
}

final fileExporterProvider = Provider<FileExporter>((ref) => const ShareExporter());

class ShareExporter implements FileExporter {
  const ShareExporter();

  @override
  Future<void> exportPng(Uint8List bytes, String fileName) async {
    await SharePlus.instance.share(ShareParams(
      files: [XFile.fromData(bytes, mimeType: 'image/png', name: fileName)],
      fileNameOverrides: [fileName],
    ));
  }
}
