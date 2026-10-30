public class AdminAuth {
    private static final String ADMIN_PASSWORD = "admin123!";

    public boolean login(String password) {
        return ADMIN_PASSWORD.equals(password);
    }
}
