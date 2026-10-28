import java.sql.*;
import java.util.concurrent.*;

public class DbConnection {
    private static final String URL = "jdbc:postgresql://localhost/db";

    // BUG 1: connection leak — no try-with-resources
    public String getUser(int id) throws SQLException {
        Connection conn = DriverManager.getConnection(URL, "user", "pass");
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT name FROM users WHERE id = " + id);
        if (rs.next()) {
            return rs.getString("name");
        }
        // conn never closed on exception path
        return null;
    }

    // BUG 2: no timeout, no pool limit
    public void bulkInsert(String[] names) throws SQLException {
        Connection conn = DriverManager.getConnection(URL, "user", "pass");
        PreparedStatement ps = conn.prepareStatement("INSERT INTO users(name) VALUES (?)");
        for (String n : names) {
            ps.setString(1, n);
            ps.executeUpdate();
        }
        conn.close();
    }

    // BUG 3: thread-unsafe shared connection
    private Connection shared;

    public void init() throws SQLException {
        shared = DriverManager.getConnection(URL, "user", "pass");
    }

    public ResultSet queryUnsafe(String sql) throws SQLException {
        return shared.createStatement().executeQuery(sql);
    }
}
