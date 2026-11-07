package ai.grantbridge.app

import android.content.ContentResolver
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.graphics.RectF
import android.view.View
import android.webkit.WebView
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import com.caverock.androidsvg.SVG
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.animation.core.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import androidx.datastore.preferences.preferencesDataStore
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.edit
import androidx.compose.runtime.collectAsState
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody

private val Navy = Color(0xFF101A35)
private val Indigo = Color(0xFF5558D9)
private val Canvas = Color(0xFFF4F6FB)
private val Ink = Color(0xFF1D2742)
private val DarkCanvas = Color(0xFF0B1220)
private val DarkSurface = Color(0xFF151F33)
private val Context.grantBridgeSettings by preferencesDataStore(name = "grantbridge_settings")
private val darkThemeKey = booleanPreferencesKey("dark_theme")
private val appLanguageKey = stringPreferencesKey("app_language")

@Composable private fun SvgTabIcon(fileName: String, selected: Boolean) {
    val context = LocalContext.current
    val tint = if (selected) Indigo else Color(0xFF858DA0)
    val tintHex = "#%06X".format(0xFFFFFF and tint.toArgb())
    val picture = remember(fileName, tintHex) {
        val svgText = context.assets.open("icons/$fileName.svg").bufferedReader().use { it.readText() }
            .replace("#111111", tintHex)
        SVG.getFromString(svgText).renderToPicture(72, 72)
    }
    Canvas(Modifier.size(24.dp)) {
        drawIntoCanvas { canvas -> canvas.nativeCanvas.drawPicture(picture, RectF(0f, 0f, size.width, size.height)) }
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val settings by applicationContext.grantBridgeSettings.data.collectAsState(initial = emptyPreferences())
            val darkTheme = settings[darkThemeKey] ?: false
            val language = settings[appLanguageKey] ?: "en"
            val scope = rememberCoroutineScope()
            GrantBridgeTheme(darkTheme) {
                GrantBridgeApp(
                    darkTheme = darkTheme,
                    languageCode = language,
                    onDarkThemeChange = { value -> scope.launch { applicationContext.grantBridgeSettings.edit { it[darkThemeKey] = value } } },
                    onLanguageChange = { value -> scope.launch { applicationContext.grantBridgeSettings.edit { it[appLanguageKey] = value } } }
                )
            }
        }
    }
}

@Composable fun GrantBridgeTheme(darkTheme: Boolean = false, content: @Composable () -> Unit) {
    val colors = if (darkTheme) darkColorScheme(
        primary = Color(0xFFB4B5FF), secondary = Color(0xFF8BDAC6), background = DarkCanvas,
        surface = DarkSurface, surfaceVariant = Color(0xFF202B42), onBackground = Color(0xFFE8ECF7),
        onSurface = Color(0xFFE8ECF7), onSurfaceVariant = Color(0xFFC1C8DA)
    ) else lightColorScheme(primary = Indigo, secondary = Color(0xFF27835E), background = Canvas, surface = Color.White, onSurface = Ink)
    MaterialTheme(colorScheme = colors, content = content)
}

class GrantBridgeViewModel : ViewModel() {
    private val api = ApiFactory.service
    var orgs by mutableStateOf(emptyList<Org>()); private set
    var grants by mutableStateOf(emptyList<Grant>()); private set
    var applications by mutableStateOf(emptyList<ApplicationRow>()); private set
    var documents by mutableStateOf(emptyList<DocumentRow>()); private set
    var notifications by mutableStateOf(emptyList<NotificationRow>()); private set
    var members by mutableStateOf(emptyList<OrganizationMember>()); private set
    var teamMessages by mutableStateOf(emptyList<TeamMessageRow>()); private set
    var selected by mutableStateOf<ApplicationDetail?>(null); private set
    var loading by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set
    var startupError by mutableStateOf(false); private set
    var signedIn by mutableStateOf(false); private set
    var account by mutableStateOf<AuthUser?>(null); private set

    fun restoreSession(context: android.content.Context) = viewModelScope.launch {
        val token = runCatching { ApiFactory.restoreToken(context) }.getOrElse { ApiFactory.clearToken(context); null }
        if (token != null) runCatching { api.profile() }.onSuccess { account = AuthUser(it.id, it.email, it.display_name); signedIn = true; refresh() }
            .onFailure { ApiFactory.clearToken(context); signedIn = false }
    }
    fun signIn(context: android.content.Context, email: String, password: String) = viewModelScope.launch {
        loading = true; error = null
        runCatching { api.login(mapOf("email" to email, "password" to password)) }
            .onSuccess { ApiFactory.saveToken(context, it.access_token); account = it.user; signedIn = true; refresh() }
            .onFailure { error = "Sign-in failed. Check the email and password, then try again." }
        loading = false
    }
    fun register(context: android.content.Context, name: String, email: String, password: String) = viewModelScope.launch {
        loading = true; error = null
        runCatching { api.register(mapOf("display_name" to name, "email" to email, "password" to password)) }
            .onSuccess { ApiFactory.saveToken(context, it.access_token); account = it.user; signedIn = true; refresh() }
            .onFailure { error = it.message ?: "Unable to create account." }
        loading = false
    }
    fun signOut(context: android.content.Context) = viewModelScope.launch {
        runCatching { api.logout() }
        ApiFactory.clearToken(context); signedIn = false; account = null; orgs = emptyList(); grants = emptyList(); applications = emptyList(); documents = emptyList(); notifications = emptyList(); members = emptyList(); teamMessages = emptyList(); selected = null; startupError = false; error = null
    }
    fun refresh() = viewModelScope.launch {
        loading = true; error = null
        runCatching {
            orgs = api.organizations()
            grants = api.grants().ifEmpty { listOf(api.seedDemo()) }
            if (orgs.isNotEmpty()) { applications = api.applications(orgs.first().id); documents = api.documents(orgs.first().id); members = api.members(orgs.first().id); teamMessages = api.teamMessages(orgs.first().id) }
            notifications = api.notifications()
        }.onSuccess { startupError = false }
            .onFailure { error = "We couldn’t connect to your workspace. Check your connection, then try again."; startupError = orgs.isEmpty() }
        loading = false
    }
    fun createOrg(name: String, country: String, mission: String) = viewModelScope.launch {
        runCatching { api.createOrganization(mapOf("name" to name, "country" to country, "mission" to mission, "org_type" to "Nonprofit")) }
            .onSuccess { refresh() }.onFailure { error = it.message }
    }
    fun searchGrants(query: String, sector: String) = viewModelScope.launch {
        runCatching { grants = api.grants(query.trim(), sector.trim()) }.onFailure { error = "Unable to search funding opportunities." }
    }
    fun addGrant(title: String, funder: String, amount: String, deadline: String, sector: String, source: String, requirements: String) = viewModelScope.launch {
        val payload = mutableMapOf<String, Any>("title" to title.trim(), "funder" to funder.trim(), "amount" to amount.trim(),
            "sector" to sector.trim(), "source_url" to source.trim(), "requirements" to requirements.lines().map { it.trim() }.filter { it.isNotBlank() })
        if (deadline.isNotBlank()) payload["deadline"] = deadline.trim()
        runCatching { api.importGrant(payload) }.onSuccess { grants = api.grants() }.onFailure { error = "Could not add opportunity. Use an HTTPS source and a valid date (YYYY-MM-DD)." }
    }
    fun updateOrg(org: Org) = viewModelScope.launch {
        runCatching { api.updateOrganization(org.id, mapOf("name" to org.name, "org_type" to org.org_type, "country" to org.country,
            "mission" to org.mission, "registration_number" to org.registration_number, "operating_regions" to org.operating_regions,
            "areas_of_operation" to org.areas_of_operation, "beneficiaries" to org.beneficiaries, "previous_projects" to org.previous_projects,
            "previous_funding" to org.previous_funding, "contact_email" to org.contact_email, "contact_phone" to org.contact_phone)) }
            .onSuccess { refresh() }.onFailure { error = "Unable to save organization profile." }
    }
    fun addMember(email: String, role: String) = viewModelScope.launch {
        val org = orgs.firstOrNull() ?: return@launch
        runCatching { api.addMember(org.id, mapOf("email" to email.trim(), "role" to role)) }.onSuccess { refresh() }
            .onFailure { error = "Member must have an account before they can be added." }
    }
    fun refreshTeamMessages() = viewModelScope.launch {
        orgs.firstOrNull()?.let { org -> runCatching { teamMessages = api.teamMessages(org.id) } }
    }
    fun sendTeamMessage(content: String) = viewModelScope.launch {
        val org = orgs.firstOrNull() ?: return@launch
        runCatching { api.sendTeamMessage(org.id, mapOf("content" to content.trim())) }
            .onSuccess { refreshTeamMessages() }.onFailure { error = "Unable to send team message. Check your connection and access." }
    }
    fun removeMember(memberId: Int) = viewModelScope.launch {
        val org = orgs.firstOrNull() ?: return@launch
        runCatching { api.removeMember(org.id, memberId) }.onSuccess { refresh() }
            .onFailure { error = "Unable to remove this team member." }
    }
    fun updateProfile(displayName: String) = viewModelScope.launch {
        runCatching { api.updateProfile(mapOf("display_name" to displayName.trim())) }
            .onSuccess { account = AuthUser(it.id, it.email, it.display_name) }
            .onFailure { error = "Unable to update your profile." }
    }
    fun changeMemberRole(memberId: Int, role: String) = viewModelScope.launch {
        val org = orgs.firstOrNull() ?: return@launch
        runCatching { api.updateMemberRole(org.id, memberId, mapOf("role" to role)) }.onSuccess { refresh() }
            .onFailure { error = "Unable to update member role." }
    }
    fun markNotificationRead(id: Int) = viewModelScope.launch {
        runCatching { api.markNotificationRead(id) }.onSuccess { notifications = api.notifications() }
    }
    fun updateTracking(status: String) = viewModelScope.launch {
        selected?.let { a -> runCatching { api.tracking(a.id, mapOf("status" to status, "reporting_requirements" to a.reporting_requirements)) }
            .onSuccess { open(a.id); refresh() }.onFailure { error = "Tracking update was rejected. Confirm the required approval step first." } }
    }
    fun start(grant: Grant) = viewModelScope.launch {
        val org = orgs.firstOrNull() ?: return@launch
        runCatching { api.startApplication(org.id, grant.id) }
            .onSuccess { refresh(); open(it.id) }.onFailure { error = it.message }
    }
    fun open(id: Int) = viewModelScope.launch { runCatching { api.application(id) }.onSuccess { selected = it }.onFailure { error = it.message } }
    fun closeApplication() { selected = null }
    fun refreshSelected() { selected?.let { open(it.id) } }
    fun handoff(issueId: Int) = viewModelScope.launch { selected?.let { a -> runCatching { api.handoffIssue(a.id, issueId) }.onSuccess { open(a.id) }.onFailure { error = it.message } } }
    fun resolve(issueId: Int) = viewModelScope.launch { selected?.let { a -> runCatching { api.resolveIssue(a.id, issueId, HumanMessage("I reviewed the revised response and verified the claim is now supported or removed.")) }.onSuccess { open(a.id) }.onFailure { error = it.message } } }
    fun approve() = viewModelScope.launch { selected?.let { a -> runCatching { api.approve(a.id, Approval(true)) }.onSuccess { open(a.id); refresh() }.onFailure { error = it.message } } }
    fun saveSection(section: Section, text: String) = viewModelScope.launch { selected?.let { a -> runCatching { api.editSection(a.id, section.id, EditSection(text)) }.onSuccess { open(a.id) }.onFailure { error = it.message } } }
    fun saveBudget(item: BudgetItem, amount: String, currency: String) = viewModelScope.launch {
        val cents = amount.toDoubleOrNull()?.times(100)?.toInt()
        if (cents == null || cents < 0) { error = "Enter a valid non-negative budget amount."; return@launch }
        selected?.let { a -> runCatching { api.editBudget(a.id, item.id, BudgetEdit(cents, currency, true)) }.onSuccess { open(a.id) }.onFailure { error = it.message } }
    }
    fun upload(resolver: ContentResolver, uri: Uri, category: String, applicationId: Int) = viewModelScope.launch {
        runCatching {
            val name = resolver.query(uri, null, null, null, null)?.use { c -> if (c.moveToFirst()) c.getString(c.getColumnIndexOrThrow(android.provider.OpenableColumns.DISPLAY_NAME)) else "supporting-document.pdf" } ?: "supporting-document.pdf"
            val bytes = resolver.openInputStream(uri)?.use { it.readBytes() } ?: throw IllegalStateException("Unable to read document")
            val body = bytes.toRequestBody((resolver.getType(uri) ?: "application/pdf").toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("file", name, body)
            api.uploadDocument(applicationId, part, category.toRequestBody("text/plain".toMediaType()))
        }.onSuccess { if (selected?.id == applicationId) open(applicationId); refresh() }.onFailure { error = it.message }
    }
    fun sendMessage(content: String, recipient: String?) = viewModelScope.launch {
        selected?.let { a -> runCatching { api.message(a.id, HumanMessage(content, recipient)) }.onSuccess { open(a.id) }.onFailure { error = it.message } }
    }
}

@Composable fun GrantBridgeApp(
    darkTheme: Boolean, languageCode: String, onDarkThemeChange: (Boolean) -> Unit, onLanguageChange: (String) -> Unit,
    vm: GrantBridgeViewModel = viewModel()
) {
    var tab by remember { mutableStateOf("Home") }
    var teamPage by remember { mutableStateOf("Overview") }
    var profilePage by remember { mutableStateOf("Profile") }
    var selectedGrant by remember { mutableStateOf<Grant?>(null) }
    var editing by remember { mutableStateOf<Section?>(null) }
    var showNotifications by remember { mutableStateOf(false) }
    val context = LocalContext.current
    LaunchedEffect(Unit) { vm.restoreSession(context) }
    var documentCategory by remember { mutableStateOf("registration_certificate") }
    var documentApplicationId by remember { mutableStateOf(0) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { vm.upload(context.contentResolver, it, documentCategory, documentApplicationId) } }
    if (!vm.signedIn) {
        AuthScreen(vm.loading, vm.error, onSignIn = { email, password -> vm.signIn(context, email, password) }, onRegister = { name, email, password -> vm.register(context, name, email, password) })
        return
    }
    Scaffold(containerColor = MaterialTheme.colorScheme.background, bottomBar = {
        NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
            listOf("Home" to "home", "Discover" to "discover", "Team" to "team", "Docs" to "documents", "Profile" to "profile").forEach { (name, icon) ->
                NavigationBarItem(selected = tab == name, onClick = { tab = name; selectedGrant = null }, icon = { SvgTabIcon(icon, tab == name) }, label = { Text(name) })
            }
        }
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Header(tab, vm.notifications.count { it.read_at == null }) { showNotifications = true }
            if (showNotifications) NotificationsDialog(vm.notifications, { showNotifications = false }) { vm.markNotificationRead(it) }
            if (!vm.startupError) vm.error?.let { Text(it, Modifier.fillMaxWidth().padding(horizontal = 18.dp), color = Color(0xFFB13E4A)) }
            if (vm.loading) LoadingStatus()
            when {
                selectedGrant != null -> GrantReport(selectedGrant!!, onBack = { selectedGrant = null }, onStart = { grant -> selectedGrant = null; tab = "Team"; teamPage = "Overview"; vm.start(grant) })
                editing != null -> EditDialog(editing!!, { editing = null }) { vm.saveSection(editing!!, it); editing = null }
                vm.selected != null && tab == "Team" -> Workspace(vm.selected!!, teamPage, { teamPage = it }, onRefresh = { vm.refreshSelected() }, onMessage = { content, recipient -> vm.sendMessage(content, recipient) }, onUpload = { documentApplicationId = vm.selected!!.id; documentCategory = "registration_certificate"; picker.launch(arrayOf("application/pdf", "image/*", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain")) }, onHandoff = { vm.handoff(it) }, onResolve = { vm.resolve(it) }, onBudgetSave = { item, amount, currency -> vm.saveBudget(item, amount, currency) }, onApprove = { vm.approve() }, onEdit = { editing = it }, onTracking = { vm.updateTracking(it) }, onBack = { vm.closeApplication() })
                vm.startupError -> ErrorPage(vm.error ?: "We couldn’t load your workspace.", onRetry = { vm.refresh() }, onSignOut = { vm.signOut(context) })
                vm.orgs.isEmpty() -> Onboarding(vm.loading) { name, country, mission -> vm.createOrg(name, country, mission) }
                tab == "Discover" -> Discover(vm.grants, { q, s -> vm.searchGrants(q, s) }, { title, funder, amount, deadline, sector, source, requirements -> vm.addGrant(title, funder, amount, deadline, sector, source, requirements) }, { selectedGrant = it })
                tab == "Team" -> TeamHub(vm.members, vm.teamMessages, vm.applications, vm.account!!.id, { vm.refreshTeamMessages() }, { vm.sendTeamMessage(it) }) { teamPage = "Overview"; vm.open(it) }
                tab == "Docs" -> DocumentCenter(vm.documents, vm.applications) { appId, category ->
                    documentApplicationId = appId
                    documentCategory = category
                    picker.launch(arrayOf("application/pdf", "image/*", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"))
                }
                tab == "Profile" -> Profile(vm.orgs.first(), vm.members, vm.account!!, profilePage, { profilePage = it }, { vm.refresh() }, { vm.updateOrg(it) }, { name -> vm.updateProfile(name) }, { email, role -> vm.addMember(email, role) }, { id, role -> vm.changeMemberRole(id, role) }, { id -> vm.removeMember(id) }, darkTheme, onDarkThemeChange, languageCode, onLanguageChange) { vm.signOut(context) }
                else -> Home(vm.orgs.first(), vm.grants, vm.applications, { selectedGrant = it }, { tab = "Discover" }, { tab = "Team"; teamPage = "Overview"; vm.applications.firstOrNull()?.let { vm.open(it.id) } })
            }
        }
    }
}

@Composable private fun Header(title: String, unread: Int, onNotifications: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(Navy).padding(horizontal = 20.dp, vertical = 18.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(34.dp).background(Indigo, RoundedCornerShape(11.dp)), contentAlignment = Alignment.Center) { Text("G", color = Color.White, fontWeight = FontWeight.Bold) }
        Spacer(Modifier.width(11.dp)); Column { Text("GRANTBRIDGE", color = Color.White, fontWeight = FontWeight.Bold); Text(title, color = Color(0xFFBCC6E5), style = MaterialTheme.typography.labelMedium) }
        Spacer(Modifier.weight(1f)); BadgedBox(badge = { if (unread > 0) Badge { Text(unread.coerceAtMost(99).toString()) } }) { IconButton(onClick = onNotifications) { Icon(Icons.Default.NotificationsNone, contentDescription = "Notifications", tint = Color.White) } }
    }
}

@Composable private fun LoadingStatus() {
    val transition = rememberInfiniteTransition(label = "grantbridge-loading")
    val rotation by transition.animateFloat(
        initialValue = 0f, targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(1100, easing = LinearEasing)), label = "spinner-rotation"
    )
    val spinnerColor = MaterialTheme.colorScheme.primary
    SurfaceCard(Modifier.padding(horizontal = 16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Canvas(Modifier.size(32.dp)) {
                rotate(rotation) {
                    drawArc(color = spinnerColor, startAngle = 40f, sweepAngle = 270f, useCenter = false,
                        style = Stroke(width = 3.5.dp.toPx(), cap = androidx.compose.ui.graphics.StrokeCap.Round))
                }
            }
            Spacer(Modifier.width(12.dp))
            Column {
                Text("Preparing your workspace", fontWeight = FontWeight.SemiBold)
                Text("Gathering your grants, documents, and team updates…", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable private fun ErrorPage(message: String, onRetry: () -> Unit, onSignOut: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.size(82.dp).background(Color(0xFFFFE9E5), CircleShape), contentAlignment = Alignment.Center) {
            Icon(Icons.Default.CloudOff, contentDescription = null, tint = Color(0xFFB44E47), modifier = Modifier.size(38.dp))
        }
        Text("We can’t reach your workspace", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 20.dp))
        Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.padding(top = 8.dp))
        Button(onClick = onRetry, modifier = Modifier.fillMaxWidth().padding(top = 22.dp)) {
            Icon(Icons.Default.Refresh, contentDescription = null); Spacer(Modifier.width(8.dp)); Text("Try again")
        }
        TextButton(onClick = onSignOut, modifier = Modifier.padding(top = 4.dp)) { Text("Sign out and use another account") }
    }
}

@Composable private fun Onboarding(loading: Boolean, onCreate: (String, String, String) -> Unit) {
    var name by remember { mutableStateOf("") }; var country by remember { mutableStateOf("") }; var mission by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().padding(22.dp), verticalArrangement = Arrangement.Center) {
        Text("Your funding workspace", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
        Text("Start with your organization profile. You can add registration evidence and more details as the team asks for them.", Modifier.padding(top = 8.dp, bottom = 22.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        OutlinedTextField(name, { name = it }, label = { Text("Organization name") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(country, { country = it }, label = { Text("Country or region") }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        OutlinedTextField(mission, { mission = it }, label = { Text("Mission") }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp), minLines = 3)
        Button(onClick = { onCreate(name, country, mission) }, enabled = name.length > 1 && !loading, modifier = Modifier.fillMaxWidth().padding(top = 18.dp)) { Text("Create organization") }
    }
}

@Composable private fun AuthScreen(loading: Boolean, error: String?, onSignIn: (String, String) -> Unit, onRegister: (String, String, String) -> Unit) {
    var registering by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }; var email by remember { mutableStateOf("") }; var password by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().background(Navy).padding(24.dp), verticalArrangement = Arrangement.Center) {
        Box(Modifier.size(52.dp).background(Indigo, RoundedCornerShape(16.dp)), contentAlignment = Alignment.Center) { Text("G", color = Color.White, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold) }
        Text("GRANTBRIDGE", color = Color.White, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 16.dp))
        Text("A thoughtful team for your next grant.", color = Color(0xFFBCC6E5), modifier = Modifier.padding(top = 6.dp, bottom = 22.dp))
        Surface(shape = RoundedCornerShape(22.dp), color = Color.White, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(if (registering) "Create your account" else "Welcome back", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Navy)
                if (registering) OutlinedTextField(name, { name = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Your name") }, singleLine = true)
                OutlinedTextField(email, { email = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Email") }, singleLine = true)
                OutlinedTextField(password, { password = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Password") }, singleLine = true, visualTransformation = PasswordVisualTransformation())
                if (registering) Text("Use at least 12 characters.", color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                error?.let { Text(it, color = Color(0xFFB13E4A), style = MaterialTheme.typography.bodySmall) }
                Button(onClick = { if (registering) onRegister(name, email, password) else onSignIn(email, password) },
                    enabled = !loading && email.contains("@") && password.isNotBlank() && (!registering || (name.length >= 2 && password.length >= 12)),
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp)) {
                    if (loading) { CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp); Spacer(Modifier.width(10.dp)); Text("Please wait…") }
                    else Text(if (registering) "Create account" else "Sign in")
                }
                TextButton(onClick = { registering = !registering }) { Text(if (registering) "Already have an account? Sign in" else "New to GRANTBRIDGE? Create an account") }
            }
        }
        Text("Your organization retains final decision authority. AI suggestions require human review.", color = Color(0xFFBCC6E5), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 18.dp))
    }
}

@Composable private fun Home(org: Org, grants: List<Grant>, apps: List<ApplicationRow>, onOpenGrant: (Grant) -> Unit, onDiscover: () -> Unit, onOpenTeam: () -> Unit) {
    LazyColumn(contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("Welcome back,", color = MaterialTheme.colorScheme.onSurfaceVariant); Text(org.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface) }
        item { Card(colors = CardDefaults.cardColors(containerColor = Navy), shape = RoundedCornerShape(22.dp)) { Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) { Column(Modifier.weight(1f)) { Text("MOVE YOUR MISSION FORWARD", color = Color(0xFFC4C9FF), style = MaterialTheme.typography.labelMedium); Text("Prepare your next grant with a team that keeps evidence and people in the loop.", color = Color.White, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(vertical = 12.dp)); Button(onClick = { grants.firstOrNull()?.let(onOpenGrant) }, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF7779FF))) { Text("Explore funding") } }; MissionIllustration(Modifier.size(76.dp)) } } }
        item { Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { Metric("Active applications", apps.size.toString(), Modifier.weight(1f)); Metric("Profile completion", "${org.completion}%", Modifier.weight(1f)) } }
        item { SectionHeader("Recommended funding", "See all", onDiscover) }
        items(grants.take(2)) { grant -> GrantCard(grant, onOpenGrant) }
        item { SectionHeader("Recent team activity", "Workspace", onOpenTeam) }
        item { SurfaceCard { Row(verticalAlignment = Alignment.CenterVertically) { AgentBadge("GB"); Spacer(Modifier.width(12.dp)); Column { Text("Application activity", fontWeight = FontWeight.SemiBold); Text("${apps.firstOrNull()?.status?.replace('_', ' ') ?: "No active workflow"} · ${apps.firstOrNull()?.current_stage?.replace('_', ' ') ?: "Start an application to begin"}", color = Color.Gray, style = MaterialTheme.typography.bodySmall) } } } }
    }
}

@Composable private fun Metric(title: String, value: String, modifier: Modifier) { SurfaceCard(modifier) { Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Indigo); Text(title, style = MaterialTheme.typography.bodySmall, color = Color.Gray) } }

@Composable private fun Discover(grants: List<Grant>, onSearch: (String, String) -> Unit, onAddGrant: (String, String, String, String, String, String, String) -> Unit, onOpenGrant: (Grant) -> Unit) {
    var query by remember { mutableStateOf("") }; var sector by remember { mutableStateOf("") }
    var adding by remember { mutableStateOf(false) }
    var title by remember { mutableStateOf("") }; var funder by remember { mutableStateOf("") }; var amount by remember { mutableStateOf("") }
    var deadline by remember { mutableStateOf("") }; var source by remember { mutableStateOf("") }; var requirements by remember { mutableStateOf("") }
    LazyColumn(contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("Discover grants", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold); Text("Sample opportunities are clearly labeled.", color = Color.Gray) }
        item { Row(verticalAlignment = Alignment.CenterVertically) { OutlinedTextField(query, { query = it }, modifier = Modifier.weight(1f), label = { Text("Search grants") }, singleLine = true); Spacer(Modifier.width(8.dp)); OutlinedTextField(sector, { sector = it }, modifier = Modifier.weight(1f), label = { Text("Sector") }, singleLine = true) }; Button(onClick = { onSearch(query, sector) }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.Search, null); Spacer(Modifier.width(8.dp)); Text("Search opportunities") } }
        item { OutlinedButton(onClick = { adding = !adding }, modifier = Modifier.fillMaxWidth()) { Text(if (adding) "Close opportunity form" else "Add an opportunity from its official source") } }
        if (adding) item { SurfaceCard { Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text("Manually add source details", fontWeight = FontWeight.Bold)
            Text("GRANTBRIDGE labels imported details as unverified until a person checks the official source.", color = Color.Gray, style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(title, { title = it }, label = { Text("Grant title") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(funder, { funder = it }, label = { Text("Funder") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(amount, { amount = it }, label = { Text("Funding amount") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(sector, { sector = it }, label = { Text("Sector") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(deadline, { deadline = it }, label = { Text("Deadline (YYYY-MM-DD, optional)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(source, { source = it }, label = { Text("Official HTTPS URL") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(requirements, { requirements = it }, label = { Text("Requirements (one per line)") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
            Button(onClick = { onAddGrant(title, funder, amount, deadline, sector, source, requirements); adding = false }, enabled = title.length >= 3 && funder.length >= 2 && sector.length >= 2 && source.startsWith("https://"), modifier = Modifier.fillMaxWidth()) { Text("Save as unverified opportunity") }
        } } }
        if (grants.isEmpty()) item { Text("No matching grants. Try a broader search.", color = Color.Gray) }
        items(grants) { GrantCard(it, onOpenGrant) }
    }
}

@Composable private fun GrantCard(g: Grant, onOpen: (Grant) -> Unit) {
    SurfaceCard {
        Row(verticalAlignment = Alignment.Top) { Box(Modifier.size(42.dp).background(Color(0xFFECEBFF), RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) { Icon(Icons.Default.School, null, tint = Indigo) }; Spacer(Modifier.width(12.dp)); Column(Modifier.weight(1f)) {
            Text(if (g.is_sample) "SAMPLE • ${g.sector.uppercase()}" else g.sector.uppercase(), color = Indigo, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
            Text(g.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 3.dp).clickable { onOpen(g) })
            Text(g.funder, color = Color.Gray); Text("${g.amount}  ·  Deadline ${g.deadline}", style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 9.dp))
            Button(onClick = { onOpen(g) }, contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)) { Text("View report and details") }
        } }
    }
}

@Composable private fun GrantReport(grant: Grant, onBack: () -> Unit, onStart: (Grant) -> Unit) {
    var showOrbFullScreen by remember { mutableStateOf(false) }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, "Back to funding") }
                Column(Modifier.weight(1f)) { Text("Funding report", fontWeight = FontWeight.Bold); Text("Opportunity overview", color = Color.Gray, style = MaterialTheme.typography.labelSmall) }
                Icon(Icons.Default.BookmarkBorder, "Save opportunity", tint = Indigo)
            }
        }
        item {
            SurfaceCard {
                Column {
                    StatusPill(if (grant.is_sample) "SAMPLE OPPORTUNITY" else grant.source_status.replace('_', ' '))
                    Text(grant.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp))
                    Text(grant.funder, color = Color.Gray, modifier = Modifier.padding(top = 4.dp))
                    Row(Modifier.fillMaxWidth().padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ReportFact("Funding", grant.amount, Modifier.weight(1f))
                        ReportFact("Deadline", grant.deadline, Modifier.weight(1f))
                    }
                    ReportFact("Sector", grant.sector, Modifier.fillMaxWidth().padding(top = 8.dp))
                }
            }
        }
        item {
            SurfaceCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CobaltSpriteWebView(Modifier.size(72.dp).clip(CircleShape))
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("Grant Scout", fontWeight = FontWeight.Bold)
                        Text("AI opportunity analyst", color = Indigo, style = MaterialTheme.typography.labelSmall)
                        Text("I’ve organized the funder details and listed requirements for your review.", color = Color.Gray, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
                        TextButton(onClick = { showOrbFullScreen = true }, contentPadding = PaddingValues(0.dp)) { Text("View AI avatar") }
                    }
                }
            }
        }
        item { Text("Application pathway", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold) }
        item {
            SurfaceCard {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Typical review stages after you start", color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                    listOf("Opportunity review", "Eligibility and evidence", "Budget review", "Draft and compliance").forEachIndexed { index, stage ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(26.dp).background(if (index == 0) Color(0xFFEAE9FF) else Color(0xFFF0F2F6), CircleShape), contentAlignment = Alignment.Center) {
                                Text(if (index == 0) "✓" else "${index + 1}", color = if (index == 0) Indigo else Color.Gray, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                            }
                            Spacer(Modifier.width(10.dp))
                            Text(stage, Modifier.weight(1f), fontWeight = if (index == 0) FontWeight.SemiBold else FontWeight.Normal)
                            if (index < 3) Text("›", color = Color.LightGray)
                        }
                    }
                }
            }
        }
        item {
            SurfaceCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Funder requirements", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    if (grant.requirements.isEmpty()) Text("No requirements are listed here yet. Check the funder’s official page.", color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                    grant.requirements.forEachIndexed { index, requirement ->
                        Row(verticalAlignment = Alignment.Top) {
                            Icon(if (index % 2 == 0) Icons.Default.FactCheck else Icons.Default.Description, null, tint = Indigo, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(8.dp)); Text(requirement, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
        item {
            SurfaceCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.VerifiedUser, null, tint = Color(0xFFAA6A24))
                    Spacer(Modifier.width(9.dp))
                    Text("Details may change. Confirm dates and eligibility on the funder’s official source. This report does not make an eligibility decision.", color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                }
                Text(grant.source_url, color = Indigo, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
            }
        }
        item { Button(onClick = { onStart(grant) }, modifier = Modifier.fillMaxWidth()) { Text("Start application with my team") } }
    }
    if (showOrbFullScreen) Dialog(
        onDismissRequest = { showOrbFullScreen = false },
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)
    ) {
        Box(Modifier.fillMaxSize().background(Color(0xFF05050F)), contentAlignment = Alignment.Center) {
            CobaltSpriteWebView(Modifier.fillMaxSize())
        }
    }
}

@Composable private fun ReportFact(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(modifier, shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
        Column(Modifier.padding(11.dp)) { Text(label, color = Color.Gray, style = MaterialTheme.typography.labelSmall); Text(value.ifBlank { "Not listed" }, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 3.dp)) }
    }
}

@Composable private fun CobaltAgentAvatar(modifier: Modifier = Modifier) {
    CobaltSpriteWebView(modifier.clip(CircleShape))
}

@Composable private fun CobaltSpriteWebView(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val assetLoader = remember(context) {
        WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
            .build()
    }
    val webView = remember(context, assetLoader) {
        WebView(context).apply {
            setBackgroundColor(android.graphics.Color.TRANSPARENT)
            setLayerType(View.LAYER_TYPE_HARDWARE, null)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = false
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.mediaPlaybackRequiresUserGesture = true
            webViewClient = object : WebViewClientCompat() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                    assetLoader.shouldInterceptRequest(request.url)
            }
            loadUrl("https://appassets.androidplatform.net/assets/cosmic-orb/index.html")
        }
    }
    DisposableEffect(webView) {
        onDispose { webView.stopLoading(); webView.destroy() }
    }
    AndroidView(factory = { webView }, modifier = modifier)
}

@Composable private fun Workspace(
    a: ApplicationDetail, page: String, onPage: (String) -> Unit, onRefresh: () -> Unit,
    onMessage: (String, String?) -> Unit, onUpload: () -> Unit, onHandoff: (Int) -> Unit,
    onResolve: (Int) -> Unit, onBudgetSave: (BudgetItem, String, String) -> Unit,
    onApprove: () -> Unit, onEdit: (Section) -> Unit, onTracking: (String) -> Unit, onBack: () -> Unit
) {
    var message by remember(a.id) { mutableStateOf("") }
    var recipient by remember(a.id) { mutableStateOf("Grant Scout") }
    var menuOpen by remember { mutableStateOf(false) }
    val pages = listOf("Overview", "Eligibility", "Budget", "Draft", "Compliance", "Activity")
    LaunchedEffect(a.id, page) { if (page == "Overview" || page == "Activity") { while (true) { delay(5000); onRefresh() } } }
    LazyColumn(contentPadding = PaddingValues(bottom = 20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, "Back to applications") }
                Column(Modifier.weight(1f)) { Text(a.grant.title, fontWeight = FontWeight.Bold, maxLines = 1); Text("${a.status.replace('_', ' ')} · ${a.current_stage}", color = Indigo, style = MaterialTheme.typography.labelSmall) }
                IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, "Refresh application") }
            }
        }
        item {
            ScrollableTabRow(selectedTabIndex = pages.indexOf(page).coerceAtLeast(0), edgePadding = 12.dp, containerColor = MaterialTheme.colorScheme.surface) {
                pages.forEach { name -> Tab(selected = page == name, onClick = { onPage(name) }, text = { Text(name) }) }
            }
        }
        when (page) {
            "Overview" -> {
                item { SurfaceCard { Column { Text("Your grant team", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); Text("One shared application room · ${if (a.switch_status == "connected") "Switch connected" else "Switch not connected"}", color = if (a.switch_status == "connected") Color(0xFF27835E) else Color(0xFFAA6A24), style = MaterialTheme.typography.bodySmall); Spacer(Modifier.height(12.dp)); Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { TeamAgentChip("GS", "Scout", a.current_stage == "scout"); TeamAgentChip("EA", "Eligibility", a.current_stage == "eligibility"); TeamAgentChip("BA", "Budget", a.current_stage == "budget"); TeamAgentChip("GW", "Writer", a.current_stage == "writing") } } } }
                item { SurfaceCard { Column { Text("Next steps", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); WorkspaceStep("Eligibility evidence", a.eligibility_assessments.isNotEmpty(), { onPage("Eligibility") }); WorkspaceStep("Human-reviewed budget", a.budget_items.isNotEmpty() && a.budget_items.all { it.approval_status == "human_approved" }, { onPage("Budget") }); WorkspaceStep("Draft sections", a.sections.isNotEmpty(), { onPage("Draft") }); WorkspaceStep("Compliance review", a.issues.isNotEmpty(), { onPage("Compliance") }) } } }
                item { SurfaceCard { Column { Text("Message your team", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); Row(verticalAlignment = Alignment.CenterVertically) { Box { TextButton(onClick = { menuOpen = true }) { Text(recipient) }; DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) { listOf("Grant Scout", "Eligibility Analyst", "Budget Analyst", "Grant Writer", "Compliance Reviewer", "Reporting Agent").forEach { name -> DropdownMenuItem(text = { Text(name) }, onClick = { recipient = name; menuOpen = false }) } } } }; Row(verticalAlignment = Alignment.CenterVertically) { OutlinedTextField(message, { message = it }, modifier = Modifier.weight(1f), label = { Text("Add information for the team") }, maxLines = 3); IconButton(onClick = { if (message.isNotBlank()) { onMessage(message, recipient); message = "" } }, enabled = message.isNotBlank()) { Icon(Icons.Default.Send, "Send") } } } } }
                item { OutlinedButton(onClick = onUpload, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.UploadFile, null); Spacer(Modifier.width(8.dp)); Text("Upload supporting document") } }
            }
            "Eligibility" -> {
                item { PageIntro("Eligibility review", "See what matches, what is missing, and the evidence behind each finding.", Icons.Default.FactCheck) }
                if (a.eligibility_assessments.isEmpty()) item { EmptyIllustrationCard("Assessment is getting ready", "The eligibility analyst will compare your organization profile with the funder’s requirements.") }
                items(a.eligibility_assessments) { assessment -> SurfaceCard { Column(verticalArrangement = Arrangement.spacedBy(7.dp)) { StatusPill(assessment.status.replace('_', ' ')); Text("Matching requirements", fontWeight = FontWeight.SemiBold); Text(assessment.matching_requirements.joinToString().ifBlank { "None recorded yet" }, style = MaterialTheme.typography.bodySmall); Text("Missing information", fontWeight = FontWeight.SemiBold); Text(assessment.missing_requirements.joinToString().ifBlank { "None recorded" }, style = MaterialTheme.typography.bodySmall); Text("Potential disqualifiers", fontWeight = FontWeight.SemiBold); Text(assessment.disqualifying_conditions.joinToString().ifBlank { "None recorded" }, style = MaterialTheme.typography.bodySmall); Text("Evidence: ${assessment.evidence.joinToString().ifBlank { "No source evidence recorded" }}", color = Color.Gray, style = MaterialTheme.typography.bodySmall); Text("Required documents: ${assessment.required_documents.joinToString().ifBlank { "None listed" }}", color = Color.Gray, style = MaterialTheme.typography.bodySmall); Text("Provenance · ${assessment.provenance.replace('_', ' ')}", color = Indigo, style = MaterialTheme.typography.labelSmall) } } }
                item { OutlinedButton(onClick = onUpload, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.UploadFile, null); Spacer(Modifier.width(8.dp)); Text("Add requested evidence") } }
            }
            "Budget" -> {
                item { PageIntro("Budget review", "Every amount is a proposal until your team checks and approves it.", Icons.Default.AccountBalanceWallet) }
                if (a.budget_items.isEmpty()) item { EmptyIllustrationCard("No budget draft yet", "The Budget Analyst will prepare categories after eligibility review.") }
                items(a.budget_items) { item -> BudgetItemCard(item, onBudgetSave) }
                if (a.budget_items.isNotEmpty()) item { SurfaceCard { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("Budget total", fontWeight = FontWeight.Bold); Text(a.budget_items.sumOf { it.amount_cents ?: 0 }.let { "%.2f".format(it / 100.0) }, color = Indigo, fontWeight = FontWeight.Bold) } } }
            }
            "Draft" -> {
                item { PageIntro("Application draft", "Edit each response and check where it came from before approval.", Icons.Default.EditNote) }
                if (a.sections.isEmpty()) item { EmptyIllustrationCard("Your draft is not ready", "The Grant Writer will build the application section by section.") }
                items(a.sections) { section -> SurfaceCard(Modifier.clickable { onEdit(section) }) { Column { Row { Text(section.title, Modifier.weight(1f), fontWeight = FontWeight.SemiBold); Text("EDIT", color = Indigo, style = MaterialTheme.typography.labelSmall) }; Text(section.content, color = Color.DarkGray, modifier = Modifier.padding(top = 7.dp), maxLines = 5); Text(section.provenance.replace('_', ' '), color = Indigo, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 7.dp)) } } }
            }
            "Compliance" -> {
                item { PageIntro("Compliance review", "Resolve reviewer findings before asking a person to approve the final draft.", Icons.Default.VerifiedUser) }
                if (a.issues.isEmpty()) item { EmptyIllustrationCard("No review findings yet", "Compliance findings will appear here with evidence and suggested corrections.") }
                items(a.issues) { issue -> SurfaceCard { Column { Text("${issue.severity.uppercase()} · ${if (issue.resolved) "HUMAN VERIFIED" else if (issue.revision_requested) "REVISION REQUESTED" else "OPEN ISSUE"}", color = if (issue.resolved) Color(0xFF27835E) else Color(0xFFB44E47), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold); Text(issue.issue, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 5.dp)); Text("Requirement: ${issue.requirement}", style = MaterialTheme.typography.bodySmall); Text("Evidence: ${issue.evidence}", color = Color.Gray, style = MaterialTheme.typography.bodySmall); Text("Suggested correction: ${issue.suggested_correction}", style = MaterialTheme.typography.bodySmall); if (!issue.resolved && !issue.revision_requested) TextButton(onClick = { onHandoff(issue.id) }) { Text("Ask ${issue.assigned_to} to revise via Switch") }; if (!issue.resolved && issue.revision_requested) TextButton(onClick = { onResolve(issue.id) }) { Text("I reviewed the correction") } } } }
                item { Button(onClick = onApprove, enabled = a.sections.isNotEmpty() && a.budget_items.isNotEmpty() && a.issues.all { it.resolved } && a.budget_items.all { it.approval_status == "human_approved" }, modifier = Modifier.fillMaxWidth()) { Text("Human approve final draft") } }
                item { Text("Approval does not submit the application.", color = Color.Gray, style = MaterialTheme.typography.bodySmall) }
            }
            else -> {
                item { PageIntro("Application activity", "A saved history of agent work, decisions, and follow-up milestones.", Icons.Default.History) }
                if (a.status == "approved") item { OutlinedButton(onClick = { onTracking("submitted") }, modifier = Modifier.fillMaxWidth()) { Text("Record that you submitted it") } }
                if (a.status == "submitted") item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { OutlinedButton(onClick = { onTracking("awarded") }, modifier = Modifier.weight(1f)) { Text("Record award") }; OutlinedButton(onClick = { onTracking("rejected") }, modifier = Modifier.weight(1f)) { Text("Record rejection") } } }
                if (a.submitted_at != null) item { SurfaceCard { Text("Submitted ${a.submitted_at}", fontWeight = FontWeight.SemiBold); Text("Reporting requirements: ${a.reporting_requirements.joinToString().ifBlank { "None recorded" }}", color = Color.Gray) } }
                items(a.events.reversed()) { event -> SurfaceCard { Row(verticalAlignment = Alignment.Top) { AgentBadge(event.actor.take(2).uppercase()); Spacer(Modifier.width(10.dp)); Column { Text("${event.actor} · ${event.event_type.replace('_', ' ')}", fontWeight = FontWeight.SemiBold); Text(event.detail, style = MaterialTheme.typography.bodySmall, color = Color.Gray); Text(event.source.uppercase(), style = MaterialTheme.typography.labelSmall, color = Indigo) } } } }
            }
        }
    }
}

@Composable private fun TeamAgentChip(initials: String, name: String, active: Boolean) {
    Surface(color = if (active) Color(0xFFECEBFF) else MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(12.dp)) { Column(Modifier.widthIn(min = 62.dp).padding(horizontal = 9.dp, vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) { Text(initials, color = Indigo, fontWeight = FontWeight.Bold); Text(name, color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.labelSmall, maxLines = 1) } }
}

@Composable private fun WorkspaceStep(label: String, done: Boolean, onClick: () -> Unit) {
    TextButton(onClick = onClick, contentPadding = PaddingValues(vertical = 3.dp)) { Text(if (done) "✓" else "○", color = if (done) Color(0xFF27835E) else Color.Gray); Spacer(Modifier.width(9.dp)); Text(label, Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurface); Icon(Icons.Default.ChevronRight, null, tint = Color.Gray) }
}

@Composable private fun PageIntro(title: String, subtitle: String, icon: androidx.compose.ui.graphics.vector.ImageVector) {
    SurfaceCard { Row(verticalAlignment = Alignment.CenterVertically) { Box(Modifier.size(48.dp).background(Color(0xFFECEBFF), RoundedCornerShape(15.dp)), contentAlignment = Alignment.Center) { Icon(icon, null, tint = Indigo) }; Spacer(Modifier.width(12.dp)); Column { Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); Text(subtitle, color = Color.Gray, style = MaterialTheme.typography.bodySmall) } } }
}

@Composable private fun StatusPill(status: String) { Surface(color = Color(0xFFECEBFF), shape = RoundedCornerShape(100.dp)) { Text(status.uppercase(), Modifier.padding(horizontal = 10.dp, vertical = 6.dp), color = Indigo, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold) } }

@Composable private fun EmptyIllustrationCard(title: String, message: String) {
    SurfaceCard { Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) { MissionIllustration(Modifier.size(112.dp)); Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); Text(message, color = Color.Gray, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 5.dp), textAlign = androidx.compose.ui.text.style.TextAlign.Center) } }
}

@Composable private fun MissionIllustration(modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val cx = size.width * .5f; val cy = size.height * .48f
        drawCircle(Color(0xFFECEBFF), radius = size.minDimension * .42f, center = androidx.compose.ui.geometry.Offset(cx, cy))
        drawCircle(Color(0xFFFFD98B), radius = size.minDimension * .13f, center = androidx.compose.ui.geometry.Offset(cx + size.width * .16f, cy - size.height * .16f))
        drawLine(Color(0xFF5A5CDD), androidx.compose.ui.geometry.Offset(cx, cy + size.height * .21f), androidx.compose.ui.geometry.Offset(cx, cy - size.height * .02f), strokeWidth = 5f, cap = androidx.compose.ui.graphics.StrokeCap.Round)
        drawLine(Color(0xFF3D9A75), androidx.compose.ui.geometry.Offset(cx, cy + size.height * .06f), androidx.compose.ui.geometry.Offset(cx - size.width * .17f, cy - size.height * .05f), strokeWidth = 5f, cap = androidx.compose.ui.graphics.StrokeCap.Round)
        drawLine(Color(0xFF3D9A75), androidx.compose.ui.geometry.Offset(cx, cy + size.height * .12f), androidx.compose.ui.geometry.Offset(cx + size.width * .17f, cy + size.height * .01f), strokeWidth = 5f, cap = androidx.compose.ui.graphics.StrokeCap.Round)
        drawLine(Color(0xFF5A5CDD), androidx.compose.ui.geometry.Offset(cx - size.width * .2f, cy + size.height * .23f), androidx.compose.ui.geometry.Offset(cx + size.width * .2f, cy + size.height * .23f), strokeWidth = 5f, cap = androidx.compose.ui.graphics.StrokeCap.Round)
    }
}

@Composable private fun BudgetItemCard(item: BudgetItem, onSave: (BudgetItem, String, String) -> Unit) {
    var amount by remember(item.id, item.amount_cents) { mutableStateOf(item.amount_cents?.let { "%.2f".format(it / 100.0) } ?: "") }
    var currency by remember(item.id, item.currency) { mutableStateOf(item.currency) }
    SurfaceCard { Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Row { Text(item.category, Modifier.weight(1f), fontWeight = FontWeight.SemiBold); Text(item.approval_status.replace('_', ' '), color = if (item.approval_status == "human_approved") Color(0xFF27835E) else Color(0xFFAA6A24), style = MaterialTheme.typography.labelSmall) }
        Text(item.description, color = Color.Gray, style = MaterialTheme.typography.bodySmall)
        Row(verticalAlignment = Alignment.CenterVertically) { OutlinedTextField(amount, { amount = it }, modifier = Modifier.weight(1f), label = { Text("Amount") }, singleLine = true); Spacer(Modifier.width(8.dp)); OutlinedTextField(currency, { currency = it.take(3).uppercase() }, modifier = Modifier.width(92.dp), label = { Text("Currency") }, singleLine = true) }
        Button(onClick = { onSave(item, amount, currency) }, enabled = amount.isNotBlank() && currency.length == 3) { Text("Save and approve amount") }
    } }
}

@Composable private fun TeamHub(
    members: List<OrganizationMember>, messages: List<TeamMessageRow>, apps: List<ApplicationRow>, userId: String,
    refreshMessages: () -> Unit, sendMessage: (String) -> Unit, openApplication: (Int) -> Unit
) {
    var draft by remember { mutableStateOf("") }
    val canSend = members.firstOrNull { it.user_id == userId }?.role != "viewer"
    LaunchedEffect(Unit) { while (true) { delay(5000); refreshMessages() } }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("Your team", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text("People and agents working together on your funding.", color = Color.Gray)
        }
        item {
            SurfaceCard {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Organization members · ${members.size}", fontWeight = FontWeight.Bold)
                    members.forEach { member ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            AgentBadge(member.display_name.split(" ").mapNotNull { it.firstOrNull()?.toString() }.take(2).joinToString("").uppercase())
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) { Text(member.display_name, fontWeight = FontWeight.SemiBold); Text(member.email, color = Color.Gray, style = MaterialTheme.typography.bodySmall) }
                            Text(member.role.replace('_', ' '), color = Indigo, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    Text("Only invited organization accounts can read this room.", color = Color.Gray, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
        item {
            SurfaceCard {
                Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Text("AI grant specialists", fontWeight = FontWeight.Bold)
                    listOf("Grant Scout", "Eligibility Analyst", "Budget Analyst", "Grant Writer", "Compliance Reviewer", "Reporting Agent").forEachIndexed { index, name ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            if (index == 0) CobaltAgentAvatar(Modifier.size(38.dp)) else AgentBadge(name.split(" ").mapNotNull { it.firstOrNull()?.toString() }.take(2).joinToString("").uppercase())
                            Spacer(Modifier.width(10.dp)); Text(name, Modifier.weight(1f), fontWeight = FontWeight.Medium)
                            Text("AI", color = Indigo, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    Text("AI suggestions stay visible for your team to review.", color = Color.Gray, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
        item {
            SurfaceCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Application workspaces", fontWeight = FontWeight.Bold)
                    if (apps.isEmpty()) Text("Start an opportunity from Discover to open a shared application workspace.", color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                    apps.forEach { app ->
                        Row(Modifier.fillMaxWidth().clickable { openApplication(app.id) }.padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.FolderOpen, null, tint = Indigo); Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) { Text("Application #${app.id}", fontWeight = FontWeight.SemiBold); Text("${app.status.replace('_', ' ')} · ${app.current_stage}", color = Color.Gray, style = MaterialTheme.typography.bodySmall) }
                            Icon(Icons.Default.ChevronRight, null, tint = Color.Gray)
                        }
                    }
                }
            }
        }
        item { Text("Team room", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold); Text("Messages are shared with all invited members and refresh automatically.", color = Color.Gray, style = MaterialTheme.typography.bodySmall) }
        if (messages.isEmpty()) item { EmptyIllustrationCard("Say hello to your team", "Share a question, update, or document detail with your organization.") }
        items(messages, key = { it.id }) { message ->
            val mine = message.sender_id == userId
            SurfaceCard {
                Row(verticalAlignment = Alignment.Top) {
                    AgentBadge(message.sender_name.split(" ").mapNotNull { it.firstOrNull()?.toString() }.take(2).joinToString("").uppercase())
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) { Text(if (mine) "You" else message.sender_name, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f)); if (mine) Text("SENT", color = Indigo, style = MaterialTheme.typography.labelSmall) }
                        Text(message.content, modifier = Modifier.padding(top = 4.dp))
                        Text(message.created_at.take(16).replace('T', ' '), color = Color.Gray, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
                    }
                }
            }
        }
        if (canSend) item {
            SurfaceCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(draft, { draft = it }, modifier = Modifier.weight(1f), label = { Text("Message the team") }, maxLines = 4)
                    IconButton(onClick = { if (draft.isNotBlank()) { sendMessage(draft); draft = "" } }, enabled = draft.isNotBlank()) { Icon(Icons.Default.Send, "Send message", tint = Indigo) }
                }
            }
        }
    }
}

@Composable private fun Profile(
    org: Org, members: List<OrganizationMember>, account: AuthUser, page: String, onPage: (String) -> Unit,
    refresh: () -> Unit, saveOrg: (Org) -> Unit, saveName: (String) -> Unit,
    addMember: (String, String) -> Unit, changeRole: (Int, String) -> Unit, removeMember: (Int) -> Unit,
    darkTheme: Boolean, onDarkThemeChange: (Boolean) -> Unit, languageCode: String, onLanguageChange: (String) -> Unit,
    signOut: () -> Unit
) {
    var displayName by remember(account.id, account.display_name) { mutableStateOf(account.display_name) }
    var orgName by remember(org.id, org.name) { mutableStateOf(org.name) }
    var orgType by remember(org.id, org.org_type) { mutableStateOf(org.org_type) }
    var country by remember(org.id, org.country) { mutableStateOf(org.country) }
    var mission by remember(org.id, org.mission) { mutableStateOf(org.mission) }
    var registration by remember(org.id, org.registration_number) { mutableStateOf(org.registration_number) }
    var regions by remember(org.id, org.operating_regions) { mutableStateOf(org.operating_regions) }
    var areas by remember(org.id, org.areas_of_operation) { mutableStateOf(org.areas_of_operation.joinToString(", ")) }
    var beneficiaries by remember(org.id, org.beneficiaries) { mutableStateOf(org.beneficiaries) }
    var projects by remember(org.id, org.previous_projects) { mutableStateOf(org.previous_projects) }
    var funding by remember(org.id, org.previous_funding) { mutableStateOf(org.previous_funding) }
    var contactEmail by remember(org.id, org.contact_email) { mutableStateOf(org.contact_email) }
    var contactPhone by remember(org.id, org.contact_phone) { mutableStateOf(org.contact_phone) }
    var inviteEmail by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("member") }
    var reminders by remember { mutableStateOf(true) }
    var activityUpdates by remember { mutableStateOf(true) }
    val pages = listOf("Profile", "Personal details", "Organization", "Team", "Settings")
    val userRole = members.firstOrNull { it.user_id == account.id }?.role ?: "member"
    val canManageTeam = userRole == "owner" || userRole == "admin"
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                pages.forEach { name -> FilterChip(selected = page == name, onClick = { onPage(name) }, label = { Text(name) }) }
            }
        }
        when (page) {
            "Profile" -> {
                item { SurfaceCard { Row(verticalAlignment = Alignment.CenterVertically) { Box(Modifier.size(58.dp).background(Color(0xFFECEBFF), CircleShape), contentAlignment = Alignment.Center) { Text(account.display_name.split(" ").mapNotNull { it.firstOrNull()?.toString() }.take(2).joinToString("").uppercase(), color = Indigo, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold) }; Spacer(Modifier.width(14.dp)); Column { Text(account.display_name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); Text(account.email, color = Color.Gray, style = MaterialTheme.typography.bodySmall); Text("${userRole.replaceFirstChar { it.uppercase() }} · ${org.name}", color = Indigo, style = MaterialTheme.typography.labelSmall) } } } }
                item { SurfaceCard { Column { Text("Your workspace", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); Text(org.mission.ifBlank { "Add your organization mission to help the team assess funding fit." }, color = Color.Gray, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 5.dp)); LinearProgressIndicator(progress = { org.completion / 100f }, modifier = Modifier.fillMaxWidth().padding(top = 12.dp), color = Indigo); Text("Profile ${org.completion}% complete", color = Indigo, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 5.dp)) } } }
                item { ProfileLink("Personal details", "Name, sign-in email and account", Icons.Default.Person) { onPage("Personal details") } }
                item { ProfileLink("Organization profile", "Mission, registration, regions and contacts", Icons.Default.Apartment) { onPage("Organization") } }
                item { ProfileLink("Team access", "${members.size} members · roles and invitations", Icons.Default.Groups) { onPage("Team") } }
                item { ProfileLink("Preferences", "Theme, language, and reminders", Icons.Default.Settings) { onPage("Settings") } }
            }
            "Personal details" -> {
                item { PageIntro("Personal details", "Your account information and organization role.", Icons.Default.Person) }
                item { SurfaceCard { Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { OutlinedTextField(displayName, { displayName = it }, label = { Text("Full name") }, modifier = Modifier.fillMaxWidth(), singleLine = true); OutlinedTextField(account.email, {}, label = { Text("Sign-in email") }, modifier = Modifier.fillMaxWidth(), readOnly = true, supportingText = { Text("Email changes require a verified account flow.") }); Text("Organization role: ${userRole.replace('_', ' ')}", color = Indigo, fontWeight = FontWeight.SemiBold); Button(onClick = { saveName(displayName) }, enabled = displayName.trim().length >= 2, modifier = Modifier.fillMaxWidth()) { Text("Save personal details") } } } }
            }
            "Organization" -> {
                item { PageIntro("Organization profile", "Complete details help the team assess eligibility without guessing.", Icons.Default.Apartment) }
                item { SurfaceCard { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(orgName, { orgName = it }, label = { Text("Organization name") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    OutlinedTextField(orgType, { orgType = it }, label = { Text("Organization type") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    OutlinedTextField(registration, { registration = it }, label = { Text("Registration number") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    OutlinedTextField(country, { country = it }, label = { Text("Country") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    OutlinedTextField(regions, { regions = it }, label = { Text("Operating regions") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(areas, { areas = it }, label = { Text("Areas of operation · separate with commas") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(beneficiaries, { beneficiaries = it }, label = { Text("Beneficiaries") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                    OutlinedTextField(mission, { mission = it }, label = { Text("Mission and objectives") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
                    OutlinedTextField(projects, { projects = it }, label = { Text("Previous projects") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                    OutlinedTextField(funding, { funding = it }, label = { Text("Previous funding") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                    OutlinedTextField(contactEmail, { contactEmail = it }, label = { Text("Organization contact email") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    OutlinedTextField(contactPhone, { contactPhone = it }, label = { Text("Organization contact phone") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    Button(onClick = { saveOrg(org.copy(name = orgName, org_type = orgType, country = country, mission = mission, registration_number = registration, operating_regions = regions, areas_of_operation = areas.split(",").map { it.trim() }.filter { it.isNotEmpty() }, beneficiaries = beneficiaries, previous_projects = projects, previous_funding = funding, contact_email = contactEmail, contact_phone = contactPhone)) }, enabled = orgName.trim().length >= 2, modifier = Modifier.fillMaxWidth()) { Text("Save organization profile") }
                } } }
            }
            "Team" -> {
                item { PageIntro("Team access", "Invite existing GRANTBRIDGE accounts and give each person the access they need.", Icons.Default.Groups) }
                if (!canManageTeam) item { Text("You can view the team. An organization owner or admin manages access.", color = Color.Gray, style = MaterialTheme.typography.bodySmall) }
                if (members.isEmpty()) item { EmptyIllustrationCard("Your team starts here", "Add a teammate who already has a GRANTBRIDGE account.") }
                items(members) { member ->
                    SurfaceCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            AgentBadge(member.display_name.split(" ").mapNotNull { it.firstOrNull()?.toString() }.take(2).joinToString("").uppercase())
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(member.display_name, fontWeight = FontWeight.SemiBold)
                                Text(member.email, color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                            }
                            if (member.role == "owner") Text("OWNER", color = Indigo, style = MaterialTheme.typography.labelSmall)
                            else if (canManageTeam) {
                                var expanded by remember(member.id) { mutableStateOf(false) }
                                Box {
                                    TextButton(onClick = { expanded = true }) { Text(member.role) }
                                    DropdownMenu(expanded, { expanded = false }) {
                                        listOf("admin", "member", "viewer").forEach { newRole ->
                                            DropdownMenuItem(text = { Text(newRole) }, onClick = { expanded = false; changeRole(member.id, newRole) })
                                        }
                                    }
                                }
                                IconButton(onClick = { removeMember(member.id) }) { Icon(Icons.Default.PersonRemove, "Remove ${member.display_name}", tint = Color(0xFFB44E47)) }
                            } else Text(member.role, color = Color.Gray, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
                if (canManageTeam) item {
                    SurfaceCard { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Invite a teammate", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        OutlinedTextField(inviteEmail, { inviteEmail = it }, label = { Text("Account email") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                        var roleMenu by remember { mutableStateOf(false) }
                        Box {
                            TextButton(onClick = { roleMenu = true }) { Text("Invite as: $role") }
                            DropdownMenu(roleMenu, { roleMenu = false }) {
                                listOf("admin", "member", "viewer").forEach { newRole ->
                                    DropdownMenuItem(text = { Text(newRole) }, onClick = { role = newRole; roleMenu = false })
                                }
                            }
                        }
                        Button(onClick = { addMember(inviteEmail, role); inviteEmail = "" }, enabled = inviteEmail.contains("@"), modifier = Modifier.fillMaxWidth()) { Text("Add team member") }
                    } }
                }
            }
            else -> {
                item { PageIntro("Preferences", "Control what appears in this app on this device.", Icons.Default.Settings) }
                item {
                    SurfaceCard {
                        Column {
                            Text("Appearance", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            PreferenceRow("Dark theme", darkTheme, onDarkThemeChange)
                            Text("Choose the look that feels comfortable for your workspace.", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                item {
                    SurfaceCard {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Language", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            Text("Preferred language · ${appLanguages.firstOrNull { it.code == languageCode }?.nativeName ?: "English"}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                            appLanguages.chunked(2).forEach { rowLanguages ->
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    rowLanguages.forEach { language ->
                                        FilterChip(
                                            selected = language.code == languageCode,
                                            onClick = { onLanguageChange(language.code) },
                                            modifier = Modifier.weight(1f),
                                            label = { Text("${language.nativeName} · ${language.englishName}", maxLines = 1) }
                                        )
                                    }
                                }
                            }
                            Text("Your selection is saved on this device.", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
                item { SurfaceCard { Column { PreferenceRow("Application reminders", reminders) { reminders = it }; PreferenceRow("Team activity updates", activityUpdates) { activityUpdates = it }; Text("These are local preview preferences; push notification delivery is not enabled yet.", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 6.dp)) } } }
                item { OutlinedButton(onClick = refresh, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.Refresh, null); Spacer(Modifier.width(8.dp)); Text("Refresh workspace") } }
                item { OutlinedButton(onClick = signOut, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFB13E4A))) { Icon(Icons.Default.Logout, null); Spacer(Modifier.width(8.dp)); Text("Sign out") } }
            }
        }
    }
}

@Composable private fun ProfileLink(title: String, subtitle: String, icon: androidx.compose.ui.graphics.vector.ImageVector, onClick: () -> Unit) {
    SurfaceCard(Modifier.clickable(onClick = onClick)) { Row(verticalAlignment = Alignment.CenterVertically) { Icon(icon, null, tint = Indigo); Spacer(Modifier.width(12.dp)); Column(Modifier.weight(1f)) { Text(title, fontWeight = FontWeight.SemiBold); Text(subtitle, color = Color.Gray, style = MaterialTheme.typography.bodySmall) }; Icon(Icons.Default.ChevronRight, null, tint = Color.Gray) } }
}

@Composable private fun PreferenceRow(title: String, enabled: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) { Text(title, Modifier.weight(1f)); Switch(checked = enabled, onCheckedChange = onChange) }
}

private data class AppLanguage(val code: String, val nativeName: String, val englishName: String)
private val appLanguages = listOf(
    AppLanguage("en", "English", "English"), AppLanguage("hi", "हिन्दी", "Hindi"),
    AppLanguage("bn", "বাংলা", "Bengali"), AppLanguage("es", "Español", "Spanish"),
    AppLanguage("fr", "Français", "French"), AppLanguage("ar", "العربية", "Arabic"),
    AppLanguage("zh", "中文", "Mandarin Chinese"), AppLanguage("pt", "Português", "Portuguese"),
    AppLanguage("sw", "Kiswahili", "Swahili"), AppLanguage("ta", "தமிழ்", "Tamil"),
    AppLanguage("ja", "日本語", "Japanese"), AppLanguage("ru", "Русский", "Russian")
)

@Composable private fun NotificationsDialog(notifications: List<NotificationRow>, onDismiss: () -> Unit, onRead: (Int) -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Notifications") }, text = {
        if (notifications.isEmpty()) Text("You’re all caught up.") else LazyColumn(modifier = Modifier.heightIn(max = 440.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(notifications) { n -> SurfaceCard(Modifier.clickable { if (n.read_at == null) onRead(n.id) }) { Column { Text(n.title, fontWeight = FontWeight.SemiBold); Text(n.body, color = Color.Gray, style = MaterialTheme.typography.bodySmall); if (n.read_at == null) Text("Tap to mark read", color = Indigo, style = MaterialTheme.typography.labelSmall) } } }
        }
    }, confirmButton = { TextButton(onClick = onDismiss) { Text("Done") } })
}

@Composable private fun DocumentCenter(documents: List<DocumentRow>, apps: List<ApplicationRow>, onUpload: (Int, String) -> Unit) {
    var query by remember { mutableStateOf("") }
    var filterCategory by remember { mutableStateOf("All documents") }
    var uploadCategory by remember { mutableStateOf("supporting_evidence") }
    var selectedDocument by remember { mutableStateOf<DocumentRow?>(null) }
    var chosenApp by remember(apps) { mutableStateOf(apps.firstOrNull()?.id) }
    var appMenu by remember { mutableStateOf(false) }
    var categoryMenu by remember { mutableStateOf(false) }
    val categories = listOf("supporting_evidence", "registration_certificate", "budget", "impact_evidence")
    val visibleDocuments = documents.filter { doc ->
        (filterCategory == "All documents" || doc.category == filterCategory) &&
            (query.isBlank() || doc.filename.contains(query, true) || doc.category.contains(query, true))
    }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("Document center", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text("Keep funder evidence, review status, and shared files together.", color = Color.Gray)
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Metric("Files", documents.size.toString(), Modifier.weight(1f))
                Metric("Text checked", documents.count { it.text_extracted }.toString(), Modifier.weight(1f))
            }
        }
        item {
            SurfaceCard {
                Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Text("Add a document", fontWeight = FontWeight.Bold)
                    if (apps.isEmpty()) Text("Start an application before uploading supporting evidence.", color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                    else {
                        Box {
                            OutlinedButton(onClick = { appMenu = true }, modifier = Modifier.fillMaxWidth()) { Text("Attach to application #${chosenApp ?: apps.first().id}") }
                            DropdownMenu(appMenu, { appMenu = false }) { apps.forEach { app -> DropdownMenuItem(text = { Text("Application #${app.id} · ${app.status.replace('_', ' ')}") }, onClick = { chosenApp = app.id; appMenu = false }) } }
                        }
                        Box {
                            OutlinedButton(onClick = { categoryMenu = true }, modifier = Modifier.fillMaxWidth()) { Text("Upload category: ${uploadCategory.replace('_', ' ').lowercase()}") }
                            DropdownMenu(categoryMenu, { categoryMenu = false }) { categories.forEach { value -> DropdownMenuItem(text = { Text(value.replace('_', ' ')) }, onClick = { uploadCategory = value; categoryMenu = false }) } }
                        }
                        Button(onClick = { chosenApp?.let { onUpload(it, uploadCategory) } }, enabled = chosenApp != null, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.UploadFile, null); Spacer(Modifier.width(8.dp)); Text("Choose a file") }
                    }
                    Text("PDF, image, Word, and text files are supported.", color = Color.Gray, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
        item { OutlinedTextField(query, { query = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Search files") }, leadingIcon = { Icon(Icons.Default.Search, null) }, singleLine = true) }
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                (listOf("All documents") + documents.map { it.category }.distinct()).forEach { value ->
                    FilterChip(selected = filterCategory == value, onClick = { filterCategory = value }, label = { Text(value.replace('_', ' ')) })
                }
            }
        }
        item { Text("Files · ${visibleDocuments.size}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold) }
        if (visibleDocuments.isEmpty()) item { EmptyIllustrationCard("No documents here yet", "Upload registration records, budgets, outcome evidence, and other required files.") }
        items(visibleDocuments, key = { it.id }) { doc ->
            SurfaceCard(Modifier.clickable { selectedDocument = doc }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Description, null, tint = Indigo, modifier = Modifier.size(28.dp)); Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(doc.filename, fontWeight = FontWeight.SemiBold)
                        Text(doc.category.replace('_', ' '), color = Color.Gray, style = MaterialTheme.typography.bodySmall)
                        Text(if (doc.text_extracted) "Text extracted · available to assigned agents" else "Stored for human review", color = if (doc.text_extracted) Color(0xFF27835E) else Color(0xFFAA6A24), style = MaterialTheme.typography.labelSmall)
                        Text("${(doc.byte_size / 1024).coerceAtLeast(1)} KB · ${doc.created_at.take(10)}", color = Color.Gray, style = MaterialTheme.typography.labelSmall)
                    }
                    Icon(Icons.Default.ChevronRight, null, tint = Color.Gray)
                }
            }
        }
        item {
            SurfaceCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Evidence checklist", fontWeight = FontWeight.Bold)
                    listOf("Registration certificate", "Itemized budget", "Impact or outcome evidence").forEach { need ->
                        val found = documents.any { it.category.contains(need.substringBefore(' ').lowercase()) || it.filename.contains(need.substringBefore(' '), true) }
                        Row(verticalAlignment = Alignment.CenterVertically) { Icon(if (found) Icons.Default.CheckCircle else Icons.Default.RadioButtonUnchecked, null, tint = if (found) Color(0xFF27835E) else Color.Gray); Spacer(Modifier.width(8.dp)); Text(need, Modifier.weight(1f)); Text(if (found) "Added" else "Optional", color = Color.Gray, style = MaterialTheme.typography.labelSmall) }
                    }
                    Text("Checklist items are suggestions. Confirm the exact evidence each funder requests.", color = Color.Gray, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
    selectedDocument?.let { doc ->
        AlertDialog(onDismissRequest = { selectedDocument = null }, title = { Text(doc.filename) }, text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Category: ${doc.category.replace('_', ' ')}")
                Text("Type: ${doc.content_type}")
                Text("Size: ${doc.byte_size} bytes")
                Text("Added: ${doc.created_at}")
                Text(if (doc.text_extracted) "Text extraction complete. Assigned agents can use this evidence." else "No text extracted. Keep this file available for human review.")
            }
        }, confirmButton = { TextButton(onClick = { selectedDocument = null }) { Text("Done") } })
    }
}

@Composable private fun EditDialog(section: Section, onDismiss: () -> Unit, onSave: (String) -> Unit) {
    var content by remember(section.id) { mutableStateOf(section.content) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(section.title) }, text = { OutlinedTextField(content, { content = it }, minLines = 5, label = { Text("Edit draft") }) }, confirmButton = { TextButton(onClick = { onSave(content) }) { Text("Save") } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}

@Composable private fun SurfaceCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.surface, shadowElevation = 1.dp) { Column(Modifier.padding(16.dp), content = content) }
}
@Composable private fun AgentBadge(text: String) { Box(Modifier.size(38.dp).background(Color(0xFFECEBFF), CircleShape), contentAlignment = Alignment.Center) { Text(text, color = Indigo, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelMedium) } }
@Composable private fun SectionHeader(title: String, action: String, onClick: () -> Unit) { Row(verticalAlignment = Alignment.CenterVertically) { Text(title, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); TextButton(onClick = onClick) { Text(action) } } }
