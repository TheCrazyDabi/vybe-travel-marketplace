package com.vybe.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.vybe.app.auth.AuthViewModel
import com.vybe.app.data.repository.SessionRepository
import com.vybe.app.data.repository.TravelRepository
import com.vybe.app.data.repository.TravelRepository
import com.vybe.app.discover.DiscoverViewModel
import com.vybe.app.navigation.Destinations
import com.vybe.app.ui.screens.DetailScreen
import com.vybe.app.ui.screens.DetailViewModel
import com.vybe.app.ui.screens.DiscoverScreen
import com.vybe.app.ui.screens.ExploreScreen
import com.vybe.app.ui.screens.ExploreViewModel
import com.vybe.app.ui.screens.LoginScreen
import com.vybe.app.ui.screens.RegisterScreen
import com.vybe.app.ui.screens.SavedScreen
import com.vybe.app.ui.screens.SavedViewModel
import com.vybe.app.ui.screens.ServerScreen
import com.vybe.app.ui.theme.VybeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as VybeApp
        setContent {
            VybeTheme {
                VybeRoot(app)
            }
        }
    }
}

private fun vmFactory(app: VybeApp): ViewModelProvider.Factory =
    object : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            val session = SessionRepository(app.settings, { app.api() })
            val travel = TravelRepository { app.api() }
            return when {
                modelClass.isAssignableFrom(AuthViewModel::class.java) ->
                    AuthViewModel(session, app.settings) as T
                modelClass.isAssignableFrom(DiscoverViewModel::class.java) ->
                    DiscoverViewModel(travel) as T
                modelClass.isAssignableFrom(ExploreViewModel::class.java) ->
                    ExploreViewModel(travel) as T
                modelClass.isAssignableFrom(DetailViewModel::class.java) ->
                    DetailViewModel(travel) as T
                modelClass.isAssignableFrom(SavedViewModel::class.java) ->
                    SavedViewModel(travel) as T
                else -> throw IllegalArgumentException("Unknown VM")
            }
        }
    }

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val TABS = listOf(
    Tab(Destinations.DISCOVER, "Discover", Icons.Filled.Home),
    Tab(Destinations.EXPLORE, "Explore", Icons.Filled.Search),
    Tab(Destinations.SAVED, "Saved", Icons.Filled.Star)
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VybeRoot(app: VybeApp) {
    val nav = rememberNavController()
    val factory = remember { vmFactory(app) }
    val authVm: AuthViewModel = viewModel(factory = factory)
    val user by authVm.user.collectAsState()
    var baseUrl by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        app.settings.baseUrlFlow().collect { baseUrl = it }
    }

    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    val inMain = route in TABS.map { it.route } || (route?.startsWith("detail/") == true)

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("✦ VYBE") },
                actions = {
                    if (user != null) {
                        IconButton(onClick = {
                            authVm.logout {
                                nav.navigate(Destinations.LOGIN) {
                                    popUpTo(Destinations.SPLASH) { inclusive = true }
                                }
                            }
                        }) { Icon(Icons.Filled.ExitToApp, contentDescription = "Log out") }
                    }
                }
            )
        },
        bottomBar = {
            if (user != null && inMain) {
                NavigationBar {
                    TABS.forEach { tab ->
                        NavigationBarItem(
                            selected = route == tab.route,
                            onClick = {
                                nav.navigate(tab.route) {
                                    popUpTo(Destinations.DISCOVER) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) }
                        )
                    }
                }
            }
        }
    ) { pad ->
        androidx.compose.foundation.layout.Box(Modifier.padding(pad)) {
            NavHost(nav, startDestination = Destinations.SPLASH) {
                composable(Destinations.SPLASH) {
                    SplashGate(app, authVm, nav)
                }
                composable(Destinations.LOGIN) {
                    LoginScreen(
                        authVm,
                        onLoggedIn = { nav.navigate(Destinations.DISCOVER) { popUpTo(Destinations.SPLASH) { inclusive = true } } },
                        onRegister = { nav.navigate(Destinations.REGISTER) },
                        onServer = { nav.navigate(Destinations.SERVER) }
                    )
                }
                composable(Destinations.REGISTER) {
                    RegisterScreen(
                        authVm,
                        onDone = { nav.navigate(Destinations.DISCOVER) { popUpTo(Destinations.SPLASH) { inclusive = true } } },
                        onLogin = { nav.popBackStack() }
                    )
                }
                composable(Destinations.SERVER) {
                    ServerScreen(authVm, baseUrl) { nav.popBackStack() }
                }
                composable(Destinations.DISCOVER) {
                    val vm: DiscoverViewModel = viewModel(factory = factory)
                    DiscoverScreen(vm) { id -> nav.navigate(Destinations.detail(id)) }
                }
                composable(Destinations.EXPLORE) {
                    val vm: ExploreViewModel = viewModel(factory = factory)
                    ExploreScreen(vm) { id -> nav.navigate(Destinations.detail(id)) }
                }
                composable(
                    Destinations.DETAIL,
                    arguments = listOf(navArgument("packageId") { type = NavType.IntType })
                ) { entry ->
                    val vm: DetailViewModel = viewModel(factory = factory)
                    DetailScreen(vm, entry.arguments?.getInt("packageId") ?: 0) { }
                }
                composable(Destinations.SAVED) {
                    val vm: SavedViewModel = viewModel(factory = factory)
                    SavedScreen(vm) { id -> nav.navigate(Destinations.detail(id)) }
                }
            }
        }
    }
}

/** Restores the server session if the cookie is still valid; else login. */
@Composable
fun SplashGate(app: VybeApp, authVm: AuthViewModel, nav: NavHostController) {
    LaunchedEffect(Unit) {
        val ok = authVm.restore()
        nav.navigate(if (ok) Destinations.DISCOVER else Destinations.LOGIN) {
            popUpTo(Destinations.SPLASH) { inclusive = true }
        }
    }
    com.vybe.app.ui.components.LoadingState("Connecting to VYBE…")
}
