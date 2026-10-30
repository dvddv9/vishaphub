import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class UserDao {
    private final Connection conn;

    public UserDao(Connection conn) {
        this.conn = conn;
    }

    public ResultSet find(String name) throws SQLException {
        Statement stmt = conn.createStatement();
        return stmt.executeQuery("SELECT id, email FROM users WHERE name = '" + name + "'");
    }
}
