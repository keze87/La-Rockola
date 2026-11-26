package ar.carpincho.rockola

import android.content.Context
import android.content.Intent
import android.graphics.Color as AndroidColor
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Reglas puras de decisión y normalización para el onboarding nativo (testeables en JVM).
 */
internal object OnboardingPolicy {
    fun shouldShowOnboarding(
        savedMusicDir: String?,
        savedTargetMode: String?,
        savedRemoteUrl: String?,
        onboardingSkipped: Boolean,
        hasShortcutAction: Boolean,
    ): Boolean {
        if (onboardingSkipped || hasShortcutAction) return false
        if (!savedMusicDir.isNullOrBlank()) return false
        if (savedTargetMode == "remote" && !savedRemoteUrl.isNullOrBlank()) return false
        return true
    }

    fun normalizeRemoteUrl(rawInput: String?): String? {
        val trimmed = rawInput?.trim()?.trimEnd('/') ?: return null
        if (trimmed.isEmpty()) return null
        val lower = trimmed.lowercase()
        if (lower.contains("://") && !lower.startsWith("http://") && !lower.startsWith("https://")) {
            return null
        }
        val withScheme = if (lower.startsWith("http://") || lower.startsWith("https://")) {
            trimmed
        } else {
            val hasPort = trimmed.substringAfterLast('/', trimmed).contains(':')
            if (hasPort) "http://$trimmed" else "http://$trimmed:1729"
        }
        return withScheme.trimEnd('/')
    }
}

/**
 * Pantalla inicial nativa en Jetpack Compose para configurar carpeta SAF local
 * o conectar a un servidor remoto sin esperar el arranque completo del WebView.
 */
class OnboardingActivity : ComponentActivity() {

    companion object {
        const val KEY_ONBOARDING_SKIPPED = "onboarding_skipped"
        const val KEY_REMOTE_URL = "remote_server_url"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(AndroidColor.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(AndroidColor.TRANSPARENT),
        )
        setContent {
            val palette = darkColorScheme(
                primary = Color(0xFFF59E0B),
                onPrimary = Color(0xFF1A120B),
                background = Color(0xFF14110F),
                surface = Color(0xFF1E1916),
                onBackground = Color(0xFFF5EFEA),
                onSurface = Color(0xFFF5EFEA),
                outline = Color(0xFF3E352F),
            )
            MaterialTheme(colorScheme = palette) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    OnboardingScreen(
                        onFolderPicked = { uri -> persistFolderAndContinue(uri) },
                        onRemoteConnected = { url -> persistRemoteAndContinue(url) },
                        onSkip = { skipAndContinue() },
                    )
                }
            }
        }
    }

    private fun persistFolderAndContinue(uri: Uri) {
        try {
            contentResolver.takePersistableUriPermission(
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION,
            )
        } catch (_: SecurityException) {
            // Algunos proveedores ya otorgan el permiso persistente al retornar
        }
        getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(RockolaForegroundService.KEY_MUSIC_DIR, uri.toString())
            .putString(RockolaForegroundService.KEY_TARGET_MODE, "host")
            .putBoolean(KEY_ONBOARDING_SKIPPED, true)
            .apply()
        RockolaForegroundService.updateMusicDir(uri.toString())
        launchMainActivity()
    }

    private fun persistRemoteAndContinue(url: String) {
        getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(RockolaForegroundService.KEY_TARGET_MODE, "remote")
            .putString(KEY_REMOTE_URL, url)
            .putBoolean(KEY_ONBOARDING_SKIPPED, true)
            .apply()
        launchMainActivity()
    }

    private fun skipAndContinue() {
        getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ONBOARDING_SKIPPED, true)
            .apply()
        launchMainActivity()
    }

    private fun launchMainActivity() {
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            },
        )
        finish()
    }
}

@Composable
private fun OnboardingScreen(
    onFolderPicked: (Uri) -> Unit,
    onRemoteConnected: (String) -> Unit,
    onSkip: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var remoteInput by remember { mutableStateOf("") }
    var remoteError by remember { mutableStateOf<String?>(null) }
    var probing by remember { mutableStateOf(false) }

    val folderLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocumentTree(),
    ) { uri ->
        if (uri != null) {
            onFolderPicked(uri)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = "La Rockola del Carpincho",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )
        Text(
            text = "Elegí cómo querés usar la app en este teléfono. Después podés cambiarlo cuando quieras.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.8f),
        )

        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "Modo Servidor Local",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = "Reproducí la música guardada en este teléfono y compartí la Rockola por Wi-Fi.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.75f),
                )
                Button(
                    onClick = { folderLauncher.launch(null) },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
                ) {
                    Text("Elegir carpeta de música", fontWeight = FontWeight.SemiBold)
                }
            }
        }

        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "Modo Cliente Remoto",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = "Controlá o escuchá desde acá una Rockola corriendo en tu PC u otro dispositivo.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.75f),
                )
                OutlinedTextField(
                    value = remoteInput,
                    onValueChange = {
                        remoteInput = it
                        remoteError = null
                    },
                    label = { Text("IP o URL (ej: 192.168.1.50)") },
                    singleLine = true,
                    isError = remoteError != null,
                    modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = MaterialTheme.colorScheme.primary,
                        unfocusedBorderColor = MaterialTheme.colorScheme.outline,
                    ),
                )
                if (remoteError != null) {
                    Text(
                        text = remoteError!!,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                OutlinedButton(
                    onClick = {
                        val normalized = OnboardingPolicy.normalizeRemoteUrl(remoteInput)
                        if (normalized == null) {
                            remoteError = "Ingresá una IP o URL válida (ej: 192.168.1.50)"
                            return@OutlinedButton
                        }
                        probing = true
                        remoteError = null
                        scope.launch {
                            val ok = probeRemoteHealth(normalized)
                            probing = false
                            if (ok) {
                                onRemoteConnected(normalized)
                            } else {
                                remoteError = "No respondió el servidor en $normalized"
                            }
                        }
                    },
                    enabled = !probing,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (probing) {
                        CircularProgressIndicator(modifier = Modifier.height(18.dp), strokeWidth = 2.dp)
                    } else {
                        Text("Probar y conectar")
                    }
                }
            }
        }

        Spacer(modifier = Modifier.weight(1f, fill = false))

        TextButton(
            onClick = onSkip,
            modifier = Modifier.align(Alignment.CenterHorizontally),
        ) {
            Text("Omitir por ahora")
        }
    }
}

private suspend fun probeRemoteHealth(baseUrl: String): Boolean = withContext(Dispatchers.IO) {
    var conn: HttpURLConnection? = null
    try {
        conn = (URL("$baseUrl/api/health").openConnection() as HttpURLConnection).apply {
            connectTimeout = 3000
            readTimeout = 3000
            requestMethod = "GET"
        }
        conn.responseCode in 200..299
    } catch (_: Exception) {
        false
    } finally {
        conn?.disconnect()
    }
}
