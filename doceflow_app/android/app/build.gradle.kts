import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Assinatura de release: a chave fica com a confeiteira (fora do repositório). Sem
// android/key.properties, o build de release usa a chave de depuração (só para testes).
val keystoreProperties = Properties()
// DOCEFLOW_SIGNING_PROPERTIES aponta para um key.properties FORA do repositório (recomendado).
val keystorePropertiesFile = System.getenv("DOCEFLOW_SIGNING_PROPERTIES")?.let { file(it) }
    ?: rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystorePropertiesFile.inputStream().use { keystoreProperties.load(it) }
}

android {
    namespace = "br.com.kikacakes.doceflow_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "br.com.kikacakes.doceflow"
        // flutter_secure_storage (Keystore) precisa do Android 6.0+ (API 23)
        minSdk = maxOf(flutter.minSdkVersion, 23)
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystorePropertiesFile.exists()) {
            create("release") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // Sem a chave da confeiteira, um APK de release assinado com a chave PÚBLICA de
            // depuração poderia ser substituído por qualquer um. Só com -PallowDebugSigning=true
            // (APK de teste, nunca para distribuir).
            val allowDebug = (project.findProperty("allowDebugSigning") as String?) == "true"
            signingConfig = when {
                keystorePropertiesFile.exists() -> signingConfigs.getByName("release")
                allowDebug -> signingConfigs.getByName("debug")
                else -> null
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

// Falha cedo e explica: release sem android/key.properties não pode ser gerado por engano.
gradle.taskGraph.whenReady {
    val wantsRelease = allTasks.any { it.name.contains("Release") && (it.name.startsWith("assemble") || it.name.startsWith("bundle")) }
    val allowDebug = (project.findProperty("allowDebugSigning") as String?) == "true"
    if (wantsRelease && !keystorePropertiesFile.exists() && !allowDebug) {
        throw GradleException(
            "APK/AAB de release precisa da chave de assinatura da confeiteira (android/key.properties). " +
            "Para um APK só de teste, use -PallowDebugSigning=true (NÃO distribua)."
        )
    }
}
