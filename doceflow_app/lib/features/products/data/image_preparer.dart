import 'dart:typed_data';

import 'package:flutter_image_compress/flutter_image_compress.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/errors/app_failure.dart';
import '../domain/product.dart';

enum PhotoSource { camera, gallery }

/// Escolhe a foto (câmera ou galeria) e prepara para o envio:
/// reduzida para cerca de 1600 px no lado menor, JPEG, SEM metadados (EXIF/GPS: a localização da casa da confeiteira
/// não pode ir parar no catálogo público).
abstract interface class PhotoPicker {
  /// null = a pessoa cancelou.
  Future<Uint8List?> pick(PhotoSource source);
}

final photoPickerProvider = Provider<PhotoPicker>((ref) => DevicePhotoPicker());

class DevicePhotoPicker implements PhotoPicker {
  DevicePhotoPicker({ImagePicker? picker}) : _picker = picker ?? ImagePicker();

  static const maxSide = 1600;
  final ImagePicker _picker;

  @override
  Future<Uint8List?> pick(PhotoSource source) async {
    final XFile? file;
    try {
      file = await _picker.pickImage(
        source: source == PhotoSource.camera ? ImageSource.camera : ImageSource.gallery,
        requestFullMetadata: false,
      );
    } catch (_) {
      throw const AppFailure('Não foi possível abrir a câmera ou a galeria. Confira as permissões do app.');
    }
    if (file == null) return null;
    final original = await file.readAsBytes();
    final Uint8List jpeg;
    try {
      jpeg = await FlutterImageCompress.compressWithList(
        original,
        minWidth: maxSide,
        minHeight: maxSide,
        quality: 85,
        format: CompressFormat.jpeg,
        keepExif: false, // remove EXIF/GPS
        autoCorrectionAngle: true,
      );
    } catch (_) {
      throw const AppFailure('Este arquivo não parece ser uma foto válida.', kind: FailureKind.validation);
    }
    if (jpeg.lengthInBytes > ProductRules.maxImageBytes) {
      throw const AppFailure('Foto grande demais mesmo depois de comprimida (máximo 5 MB).',
          kind: FailureKind.validation);
    }
    return jpeg;
  }
}
